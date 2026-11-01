import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.services.hydration import day_bounds_utc
from tests.conftest import auth, last_code, register

API = "/api/v1"


def add(client, h, ml, **kw):
    body = {"client_id": str(kw.pop("client_id", uuid.uuid4())), "volume_ml": ml, **kw}
    return client.post(f"{API}/hydration/entries", headers=h, json=body)


def test_add_entries_and_today_total(client, verified):
    h, _ = verified
    assert add(client, h, 250).status_code == 201
    assert add(client, h, 500).status_code == 201
    today = client.get(f"{API}/hydration/today", headers=h).json()
    assert today["total_ml"] == 750 and today["goal_ml"] == 2000
    assert today["progress"] == 0.375 and today["goal_met"] is False
    assert len(today["entries"]) == 2 and today["timezone"] == "Africa/Johannesburg"


def test_same_client_id_is_idempotent(client, verified):
    h, _ = verified
    cid = uuid.uuid4()
    first = add(client, h, 250, client_id=cid)
    replay = add(client, h, 250, client_id=cid)
    assert first.status_code == 201 and replay.status_code == 200
    assert first.json()["id"] == replay.json()["id"]
    assert client.get(f"{API}/hydration/today", headers=h).json()["total_ml"] == 250


def test_undo_is_soft_delete_and_idempotent(client, verified):
    h, _ = verified
    cid = uuid.uuid4()
    add(client, h, 300, client_id=cid)
    for _ in range(2):
        res = client.delete(f"{API}/hydration/entries/{cid}", headers=h)
        assert res.status_code == 200 and res.json()["deleted"] is True
    assert client.get(f"{API}/hydration/today", headers=h).json()["total_ml"] == 0
    assert client.delete(f"{API}/hydration/entries/{uuid.uuid4()}", headers=h).status_code == 404
    # Re-sending the deleted entry (offline replay) must not resurrect it.
    assert add(client, h, 300, client_id=cid).json()["deleted"] is True


def test_entry_validation(client, verified):
    h, _ = verified
    assert add(client, h, 0).status_code == 422
    assert add(client, h, 5001).status_code == 422
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    assert add(client, h, 200, consumed_at=future).json()["error"]["code"] == "future_timestamp"
    old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    assert add(client, h, 200, consumed_at=old).json()["error"]["code"] == "too_old"
    assert add(client, h, 200, consumed_at="2026-01-01T10:00:00").status_code == 422  # naive time rejected


def test_users_cannot_see_or_delete_each_others_entries(client, verified):
    h, _ = verified
    cid = uuid.uuid4()
    add(client, h, 400, client_id=cid)
    other = register(client, email="bob@example.com")
    oh = auth(other["access_token"])
    client.post(f"{API}/auth/verify-email", json={"code": last_code("bob@example.com")}, headers=oh)
    assert client.get(f"{API}/hydration/today", headers=oh).json()["total_ml"] == 0
    assert client.delete(f"{API}/hydration/entries/{cid}", headers=oh).status_code == 404
    # Bob reusing Ada's client_id creates Bob's own entry, it doesn't return Ada's.
    res = add(client, oh, 100, client_id=cid)
    assert res.status_code == 201 and res.json()["volume_ml"] == 100


def test_goal_change_does_not_rewrite_history(client, verified, db_factory):
    h, _ = verified
    from sqlalchemy import select

    from app.models.hydration import HydrationGoal

    with db_factory() as db:  # the signup goal was "set" 3 days ago
        goal = db.execute(select(HydrationGoal)).scalar_one()
        goal.effective_from -= timedelta(days=3)
        db.commit()
    assert client.put(f"{API}/hydration/goal", headers=h, json={"daily_goal_ml": 3000}).status_code == 200
    days = client.get(f"{API}/hydration/history", headers=h).json()["days"]
    assert len(days) == 7
    assert days[-1]["goal_ml"] == 3000
    assert days[-2]["goal_ml"] == 2000
    assert client.get(f"{API}/hydration/goal", headers=h).json()["daily_goal_ml"] == 3000
    assert client.put(f"{API}/hydration/goal", headers=h, json={"daily_goal_ml": 100}).status_code == 422


def test_history_buckets_by_local_day(client, verified):
    h, _ = verified
    tz = ZoneInfo("Africa/Johannesburg")  # UTC+2
    today = datetime.now(tz).date()
    yesterday = today - timedelta(days=1)
    # 23:30 local yesterday is 21:30 UTC yesterday; 00:30 local today is 22:30 UTC yesterday.
    late = datetime.combine(yesterday, datetime.min.time(), tz) + timedelta(hours=23, minutes=30)
    early = datetime.combine(today, datetime.min.time(), tz) + timedelta(minutes=30)
    add(client, h, 111, consumed_at=late.isoformat())
    if early < datetime.now(tz):
        add(client, h, 222, consumed_at=early.isoformat())
    days = {d["date"]: d for d in client.get(f"{API}/hydration/history", headers=h,
                                             params={"from": str(yesterday), "to": str(today)}).json()["days"]}
    assert days[str(yesterday)]["total_ml"] == 111
    detail = client.get(f"{API}/hydration/days/{yesterday}", headers=h).json()
    assert detail["total_ml"] == 111 and len(detail["entries"]) == 1


def test_history_range_limits(client, verified):
    h, _ = verified
    assert client.get(f"{API}/hydration/history", headers=h,
                      params={"from": "2026-05-02", "to": "2026-05-01"}).status_code == 422
    assert client.get(f"{API}/hydration/history", headers=h,
                      params={"from": "2024-01-01", "to": "2026-01-01"}).status_code == 422


def test_dst_day_bounds():
    ny = ZoneInfo("America/New_York")
    start, end = day_bounds_utc(date(2026, 3, 8), ny)  # spring forward: 23-hour day
    assert end - start == timedelta(hours=23)
    start, end = day_bounds_utc(date(2026, 11, 1), ny)  # fall back: 25-hour day
    assert end - start == timedelta(hours=25)
