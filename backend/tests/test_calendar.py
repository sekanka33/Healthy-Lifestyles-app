"""Google Calendar + recommendations. Google is replaced by a fake; tests never call it for real."""

import uuid
from datetime import datetime, time, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.models.billing import SubscriptionEntitlement
from app.models.integrations import CalendarEventRecord, OAuthConnection, OAuthState
from app.services import google_calendar as google
from app.services.google_calendar import GoogleClient, GoogleError

API = "/api/v1"
TZ = ZoneInfo("Africa/Johannesburg")


class FakeGoogle(GoogleClient):
    def __init__(self):
        super().__init__("cid", "secret", "http://localhost:8000/api/v1/calendar/oauth/callback")
        self.calls: list[str] = []
        self.granted = google.SCOPE_FREEBUSY
        self.busy: list[tuple[str, str]] = []
        self.revoked = False
        self.events: list[dict] = []

    def exchange_code(self, code, verifier):
        self.calls.append(f"exchange:{code}:{len(verifier)}")
        if code == "bad":
            raise GoogleError("invalid_grant", auth_revoked=True)
        return {"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600, "scope": self.granted}

    def refresh(self, refresh_token):
        self.calls.append("refresh")
        if self.revoked:
            raise GoogleError("invalid_grant", auth_revoked=True)
        return {"access_token": "at-2", "expires_in": 3600}

    def revoke(self, token):
        self.calls.append(f"revoke:{token}")

    def free_busy(self, access_token, start, end, calendar_ids):
        self.calls.append(f"freebusy:{access_token}")
        if self.revoked:
            raise GoogleError("unauthorised", auth_revoked=True)
        return self.busy

    def create_event(self, access_token, **kw):
        self.calls.append("create_event")
        self.events.append(kw)
        return {"id": f"evt-{len(self.events)}"}


@pytest.fixture
def g(monkeypatch):
    fake = FakeGoogle()
    monkeypatch.setattr(google, "get_client", lambda: fake)
    return fake


def connect(client, h, g, code="good"):
    url = client.post(f"{API}/calendar/connect", headers=h).json()["auth_url"]
    q = parse_qs(urlparse(url).query)
    res = client.get(f"{API}/calendar/oauth/callback", params={"state": q["state"][0], "code": code}, follow_redirects=False)
    return url, q, res


def tomorrow():
    return datetime.now(TZ).date() + timedelta(days=1)


def iso(day, h, m=0):
    return datetime.combine(day, time(h, m), TZ).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def test_connect_uses_pkce_minimal_scope_and_encrypts_tokens(client, verified, g, db_factory):
    h, _ = verified
    url, q, res = connect(client, h, g)
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert q["scope"] == [google.SCOPE_FREEBUSY]  # least privilege at first connect
    assert q["code_challenge_method"] == ["S256"] and q["access_type"] == ["offline"]
    assert res.status_code == 302 and res.headers["location"] == "lifepulse://calendar-connected?status=ok"
    with db_factory() as db:
        c = db.execute(select(OAuthConnection)).scalar_one()
        st = db.execute(select(OAuthState)).scalar_one()
    assert "rt-1" not in (c.refresh_token_enc or "") and "at-1" not in (c.access_token_enc or "")
    assert q["state"][0] not in st.state_hash  # only a hash of the state is stored
    s = client.get(f"{API}/calendar/status", headers=h).json()
    assert s == {"connected": True, "status": "active", "can_read_free_busy": True, "can_add_events": False}


def test_state_is_single_use_and_unknown_states_fail(client, verified, g):
    h, _ = verified
    url, q, _ = connect(client, h, g)
    replay = client.get(f"{API}/calendar/oauth/callback", params={"state": q["state"][0], "code": "good"}, follow_redirects=False)
    assert replay.headers["location"].endswith("status=error")
    forged = client.get(f"{API}/calendar/oauth/callback", params={"state": "made-up", "code": "x"}, follow_redirects=False)
    assert forged.headers["location"].endswith("status=error")
    assert sum(c.startswith("exchange:good:") for c in g.calls) == 1
    verifier_len = int(g.calls[0].rsplit(":", 1)[1])
    assert 43 <= verifier_len <= 128  # RFC 7636 PKCE verifier length


def test_denied_consent_and_expired_state(client, verified, g, db_factory):
    h, _ = verified
    url = client.post(f"{API}/calendar/connect", headers=h).json()["auth_url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    denied = client.get(f"{API}/calendar/oauth/callback", params={"state": state, "error": "access_denied"}, follow_redirects=False)
    assert denied.headers["location"].endswith("status=denied")
    url = client.post(f"{API}/calendar/connect", headers=h).json()["auth_url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    with db_factory() as db:
        st = db.execute(select(OAuthState).where(OAuthState.consumed_at.is_(None))).scalar_one()
        st.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    late = client.get(f"{API}/calendar/oauth/callback", params={"state": state, "code": "good"}, follow_redirects=False)
    assert late.headers["location"].endswith("status=error")
    assert client.get(f"{API}/calendar/status", headers=h).json()["connected"] is False


def test_free_slots_without_and_with_calendar(client, verified, g):
    h, _ = verified
    d = tomorrow()
    open_day = client.get(f"{API}/calendar/free-slots", headers=h, params={"date": str(d)}).json()
    assert open_day["calendar_used"] is False and len(open_day["slots"]) == 1  # 06:30–22:00
    assert open_day["slots"][0]["minutes"] == 15 * 60 + 30
    connect(client, h, g)
    g.busy = [(iso(d, 9), iso(d, 17))]
    busy_day = client.get(f"{API}/calendar/free-slots", headers=h, params={"date": str(d)}).json()
    assert busy_day["calendar_used"] is True
    assert [s["minutes"] for s in busy_day["slots"]] == [150, 300]  # 06:30–09:00, 17:00–22:00


def test_expired_access_token_is_refreshed_and_revocation_handled(client, verified, g, db_factory):
    h, _ = verified
    connect(client, h, g)
    with db_factory() as db:
        c = db.execute(select(OAuthConnection)).scalar_one()
        c.access_token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    client.get(f"{API}/calendar/free-slots", headers=h, params={"date": str(tomorrow())})
    assert "refresh" in g.calls and "freebusy:at-2" in g.calls
    g.revoked = True
    with db_factory() as db:
        c = db.execute(select(OAuthConnection)).scalar_one()
        c.access_token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    r = client.get(f"{API}/calendar/free-slots", headers=h, params={"date": str(tomorrow())})
    assert r.status_code == 409 and r.json()["error"]["code"] == "calendar_reconnect"
    assert client.get(f"{API}/calendar/status", headers=h).json()["status"] == "revoked"


def test_disconnect_revokes_at_google_and_deletes_tokens(client, verified, g, db_factory):
    h, _ = verified
    connect(client, h, g)
    assert client.delete(f"{API}/calendar", headers=h).status_code == 204
    assert "revoke:rt-1" in g.calls
    with db_factory() as db:
        assert db.execute(select(OAuthConnection)).scalar_one_or_none() is None


def test_free_plan_gets_water_breaks_only(client, verified, g):
    h, _ = verified
    recs = client.get(f"{API}/recommendations", headers=h, params={"date": str(tomorrow())}).json()
    assert recs["items"] and all(r["kind"] == "hydration" for r in recs["items"])
    assert recs["premium_ideas_available"] >= 1


@pytest.fixture
def premium(client, verified, db_factory):
    h, s = verified
    with db_factory() as db:
        db.add(SubscriptionEntitlement(user_id=uuid.UUID(s["user"]["id"]), status="active", expires_at=None))
        db.commit()
    return h


def test_premium_activity_ideas_and_scheduling_with_incremental_consent(client, premium, g, db_factory):
    h = premium
    client.patch(f"{API}/me/scheduling-preferences", headers=h,
                 json={"preferred_activities": ["running"], "preferred_activity_times": ["evening"]})
    connect(client, h, g)
    recs = client.get(f"{API}/recommendations", headers=h, params={"date": str(tomorrow())}).json()
    run = next(r for r in recs["items"] if r["kind"] == "running")
    assert recs["premium_ideas_available"] == 0
    # First "add to calendar" asks for the extra permission instead of failing silently.
    r = client.post(f"{API}/recommendations/{run['id']}/schedule", headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "needs_calendar_permission"
    scope = parse_qs(urlparse(r.json()["error"]["auth_url"]).query)["scope"][0].split()
    assert google.SCOPE_EVENTS in scope
    g.granted = f"{google.SCOPE_FREEBUSY} {google.SCOPE_EVENTS}"
    connect(client, h, g)
    assert client.get(f"{API}/calendar/status", headers=h).json()["can_add_events"] is True
    done = client.post(f"{API}/recommendations/{run['id']}/schedule", headers=h)
    assert done.status_code == 200 and done.json()["status"] == "scheduled"
    again = client.post(f"{API}/recommendations/{run['id']}/schedule", headers=h)  # double tap
    assert again.status_code == 200 and g.calls.count("create_event") == 1
    with db_factory() as db:
        assert len(db.execute(select(CalendarEventRecord)).scalars().all()) == 1
    # A refresh keeps the scheduled item and doesn't duplicate it.
    later = client.get(f"{API}/recommendations", headers=h, params={"date": str(tomorrow())}).json()
    assert [r["status"] for r in later["items"] if r["id"] == run["id"]] == ["scheduled"]


def test_scheduling_is_premium_and_dismiss_hides_items(client, verified, g):
    h, _ = verified
    recs = client.get(f"{API}/recommendations", headers=h, params={"date": str(tomorrow())}).json()
    first = recs["items"][0]
    assert client.post(f"{API}/recommendations/{first['id']}/schedule", headers=h).status_code == 402
    assert client.post(f"{API}/recommendations/{first['id']}/dismiss", headers=h).json()["status"] == "dismissed"
    again = client.get(f"{API}/recommendations", headers=h, params={"date": str(tomorrow())}).json()
    assert first["id"] not in [r["id"] for r in again["items"]]
    assert all((r["kind"], r["start"]) != (first["kind"], first["start"]) for r in again["items"])


def test_scheduling_preferences_validation(client, verified):
    h, _ = verified
    p = client.get(f"{API}/me/scheduling-preferences", headers=h).json()
    assert p["sleep_start"] == "22:00:00" and p["sleep_end"] == "06:30:00"
    assert client.patch(f"{API}/me/scheduling-preferences", headers=h,
                        json={"working_hours_start": "09:00:00"}).status_code == 422
    ok = client.patch(f"{API}/me/scheduling-preferences", headers=h,
                      json={"working_hours_start": "09:00:00", "working_hours_end": "17:00:00", "min_free_slot_minutes": 30})
    assert ok.status_code == 200 and ok.json()["min_free_slot_minutes"] == 30
    assert client.patch(f"{API}/me/scheduling-preferences", headers=h,
                        json={"preferred_activities": ["swimming"]}).status_code == 422
    assert client.patch(f"{API}/me/scheduling-preferences", headers=h,
                        json={"sleep_start": "06:30:00"}).status_code == 422


def test_calendar_not_configured_is_a_clean_503(client, verified):
    h, _ = verified
    r = client.post(f"{API}/calendar/connect", headers=h)
    assert r.status_code == 503 and r.json()["error"]["code"] == "calendar_not_configured"
