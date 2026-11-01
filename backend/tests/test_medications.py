import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.models.billing import SubscriptionEntitlement
from app.models.medication import Medication
from app.models.user import User
from app.services.medication_schedule import Schedule, is_occurrence, occurrences
from tests.conftest import auth, last_code, register

API = "/api/v1/medications"
TZ = "Africa/Johannesburg"
JHB = ZoneInfo(TZ)


# ---------------------------------------------------------------- schedule engine (pure)

def sched(**kw) -> Schedule:
    base = dict(schedule_type="daily", times=["08:00", "20:00"], timezone=TZ, start_date=date(2026, 1, 1))
    return Schedule(**{**base, **kw})


def test_daily_twice_a_day():
    occ = occurrences(sched(), date(2026, 1, 1), date(2026, 1, 3))
    assert len(occ) == 6
    assert occ[0] == datetime(2026, 1, 1, 6, 0, tzinfo=timezone.utc)  # 08:00 SAST = 06:00 UTC


def test_specific_days_every_n_days_and_date_bounds():
    mon_wed = occurrences(sched(schedule_type="specific_days", times=["09:00"], days_of_week=[1, 3]),
                          date(2026, 1, 5), date(2026, 1, 11))  # Mon 5 .. Sun 11
    assert [o.astimezone(JHB).isoweekday() for o in mon_wed] == [1, 3]
    every3 = occurrences(sched(schedule_type="every_n_days", times=["09:00"], interval_days=3),
                         date(2026, 1, 1), date(2026, 1, 10))
    assert [o.astimezone(JHB).day for o in every3] == [1, 4, 7, 10]
    bounded = occurrences(sched(times=["09:00"], start_date=date(2026, 1, 3), end_date=date(2026, 1, 4)),
                          date(2026, 1, 1), date(2026, 1, 10))
    assert len(bounded) == 2
    assert occurrences(sched(schedule_type="as_needed", times=[]), date(2026, 1, 1), date(2026, 1, 9)) == []


def test_discontinued_stops_future_doses():
    s = sched(times=["08:00"], discontinued_at=datetime(2026, 1, 3, 12, 0, tzinfo=timezone.utc))
    assert len(occurrences(s, date(2026, 1, 1), date(2026, 1, 9))) == 3


def test_dst_keeps_local_wall_clock_and_never_drops_or_doubles_a_dose():
    ny = "America/New_York"
    s = sched(times=["08:00"], timezone=ny)
    before, after = occurrences(s, date(2026, 3, 7), date(2026, 3, 9))[0::2]
    assert before.hour == 13 and after.hour == 12  # 08:00 EST = 13Z, 08:00 EDT = 12Z
    gap = occurrences(sched(times=["02:30"], timezone=ny), date(2026, 3, 8), date(2026, 3, 8))
    assert len(gap) == 1 and gap[0].astimezone(ZoneInfo(ny)).hour == 3  # moved to 03:30, not dropped
    fold = occurrences(sched(times=["01:30"], timezone=ny), date(2026, 11, 1), date(2026, 11, 1))
    assert len(fold) == 1  # ambiguous hour: one dose, not two


def test_is_occurrence():
    s = sched()
    assert is_occurrence(s, datetime(2026, 1, 2, 18, 0, tzinfo=timezone.utc))  # 20:00 local
    assert not is_occurrence(s, datetime(2026, 1, 2, 18, 1, tzinfo=timezone.utc))


# ---------------------------------------------------------------- API

@pytest.fixture
def premium(client, verified, db_factory):
    h, s = verified
    with db_factory() as db:
        db.add(SubscriptionEntitlement(user_id=uuid.UUID(s["user"]["id"]), status="active",
                                       expires_at=datetime.now(timezone.utc) + timedelta(days=30)))
        db.commit()
    return h


def med(client, h, **kw):
    body = {"name": "Metformin", "dosage_instructions": "500 mg with breakfast and dinner",
            "schedule_type": "daily", "times": ["08:00", "20:00"], **kw}
    return client.post(API, headers=h, json=body)


def test_free_users_get_402_but_can_list_and_delete(client, verified, premium, db_factory):
    h = premium
    m = med(client, h).json()
    with db_factory() as db:  # subscription lapses
        db.execute(select(SubscriptionEntitlement)).scalar_one().status = "expired"
        db.commit()
    assert med(client, h).status_code == 402
    assert client.get(f"{API}/schedule", headers=h).json()["error"]["code"] == "premium_required"
    assert len(client.get(API, headers=h).json()) == 1  # their data is still visible …
    assert client.delete(f"{API}/{m['id']}", headers=h).status_code == 204  # … and deletable
    assert client.get(API, headers=h).json() == []


def test_guests_and_unverified_users_are_rejected(client):
    assert client.get(API).status_code == 401
    s = register(client, email="new@example.com")
    assert client.get(API, headers=auth(s["access_token"])).status_code == 403


def test_create_keeps_instructions_verbatim_and_defaults(client, premium):
    text = "  Take 1 tablet (5 mg) at night. Do NOT exceed 2 in 24h.  "
    res = med(client, premium, dosage_instructions=text, times=["20:00", "08:00", "08:00"])
    assert res.status_code == 201
    body = res.json()
    assert body["dosage_instructions"] == text.strip()  # only surrounding whitespace is trimmed
    assert body["times"] == ["08:00", "20:00"]
    assert body["timezone"] == TZ and body["active"] is True
    assert body["start_date"] == str(datetime.now(JHB).date())


@pytest.mark.parametrize("bad", [
    {"times": []},
    {"times": ["8am"]},
    {"times": ["24:00"]},
    {"schedule_type": "specific_days"},
    {"schedule_type": "specific_days", "days_of_week": [0]},
    {"schedule_type": "every_n_days"},
    {"start_date": "2026-05-02", "end_date": "2026-05-01"},
    {"timezone": "Mars/Olympus"},
    {"name": ""},
    {"dosage_instructions": ""},
])
def test_create_validation(client, premium, bad):
    assert med(client, premium, **bad).status_code == 422


def test_schedule_lists_doses_and_never_assumes_taken(client, premium):
    m = med(client, premium, times=["00:01", "23:59"]).json()
    today = client.get(f"{API}/schedule", headers=premium).json()
    assert [d["medication_id"] for d in today] == [m["id"], m["id"]]
    assert today[0]["status"] == "unrecorded"  # 00:01 has passed; nothing logged ≠ taken
    assert today[1]["status"] in ("upcoming", "unrecorded")
    assert today[0]["dosage_instructions"] == m["dosage_instructions"]


def test_record_correct_and_clear_a_dose(client, premium):
    m = med(client, premium, times=["00:01"]).json()
    dose = client.get(f"{API}/schedule", headers=premium).json()[0]
    url = f"{API}/{m['id']}/doses"
    first = client.put(url, headers=premium, json={"scheduled_for": dose["scheduled_for"], "status": "taken"})
    assert first.status_code == 201 and first.json()["status"] == "taken"
    fix = client.put(url, headers=premium, json={"scheduled_for": dose["scheduled_for"], "status": "skipped",
                                                 "note": "felt unwell"})
    assert fix.status_code == 200 and fix.json()["status"] == "skipped"
    assert client.get(f"{API}/schedule", headers=premium).json()[0]["status"] == "skipped"
    assert client.delete(url, headers=premium, params={"scheduled_for": dose["scheduled_for"]}).status_code == 204
    assert client.get(f"{API}/schedule", headers=premium).json()[0]["status"] == "unrecorded"


def test_dose_must_match_the_schedule(client, premium):
    m = med(client, premium, times=["00:01"]).json()
    dose = client.get(f"{API}/schedule", headers=premium).json()[0]
    off = (datetime.fromisoformat(dose["scheduled_for"]) + timedelta(minutes=7)).isoformat()
    res = client.put(f"{API}/{m['id']}/doses", headers=premium, json={"scheduled_for": off, "status": "taken"})
    assert res.json()["error"]["code"] == "not_scheduled"
    tomorrow = (datetime.fromisoformat(dose["scheduled_for"]) + timedelta(days=1)).isoformat()
    res = client.put(f"{API}/{m['id']}/doses", headers=premium, json={"scheduled_for": tomorrow, "status": "taken"})
    assert res.json()["error"]["code"] == "future_dose"


def test_as_needed_doses(client, premium):
    m = med(client, premium, schedule_type="as_needed", times=[], name="Ibuprofen",
            dosage_instructions="200 mg when needed, max 3 per day").json()
    url = f"{API}/{m['id']}/doses"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    assert client.put(url, headers=premium, json={"scheduled_for": now.isoformat(), "status": "taken"}).status_code == 201
    assert client.put(url, headers=premium, json={"scheduled_for": now.isoformat(), "status": "skipped"}).status_code == 422
    future = (now + timedelta(hours=1)).isoformat()
    assert client.put(url, headers=premium, json={"scheduled_for": future, "status": "taken"}).status_code == 422
    today = client.get(f"{API}/schedule", headers=premium).json()
    assert [d["status"] for d in today] == ["taken"]
    adh = client.get(f"{API}/adherence", headers=premium).json()["medications"][0]
    assert adh["as_needed_taken"] == 1 and adh["scheduled"] == 0 and adh["adherence"] is None


def test_adherence_separates_unrecorded_from_missed(client, premium, db_factory):
    m = med(client, premium, times=["00:01"]).json()
    with db_factory() as db:  # started 3 days ago
        row = db.get(Medication, uuid.UUID(m["id"]))
        row.start_date -= timedelta(days=3)
        db.commit()
    today = datetime.now(JHB).date()
    doses = client.get(f"{API}/schedule", headers=premium,
                       params={"from": str(today - timedelta(days=3)), "to": str(today)}).json()
    assert len(doses) == 4
    url = f"{API}/{m['id']}/doses"
    client.put(url, headers=premium, json={"scheduled_for": doses[0]["scheduled_for"], "status": "taken"})
    client.put(url, headers=premium, json={"scheduled_for": doses[1]["scheduled_for"], "status": "missed"})
    client.put(url, headers=premium, json={"scheduled_for": doses[2]["scheduled_for"], "status": "taken"})
    r = client.get(f"{API}/adherence", headers=premium).json()["medications"][0]
    assert (r["scheduled"], r["taken"], r["missed"], r["unrecorded"]) == (4, 2, 1, 1)
    assert r["adherence"] == 0.5


def test_update_revalidates_and_discontinue_resume(client, premium):
    m = med(client, premium).json()
    url = f"{API}/{m['id']}"
    assert client.patch(url, headers=premium, json={"schedule_type": "specific_days"}).status_code == 422
    res = client.patch(url, headers=premium, json={"schedule_type": "specific_days", "days_of_week": [1, 5]})
    assert res.status_code == 200 and res.json()["days_of_week"] == [1, 5]
    res = client.patch(url, headers=premium, json={"schedule_type": "daily"})
    assert res.json()["days_of_week"] is None  # stale fields from the old schedule are cleared
    stopped = client.post(f"{url}/discontinue", headers=premium).json()
    assert stopped["active"] is False
    future = client.get(f"{API}/schedule", headers=premium,
                        params={"from": str(datetime.now(JHB).date() + timedelta(days=1))}).json()
    assert future == []
    assert client.post(f"{url}/resume", headers=premium).json()["active"] is True


def test_cannot_touch_another_users_medication(client, premium, db_factory):
    m = med(client, premium).json()
    s = register(client, email="mallory@example.com")
    hm = auth(s["access_token"])
    client.post("/api/v1/auth/verify-email", json={"code": last_code("mallory@example.com")}, headers=hm)
    with db_factory() as db:
        uid = db.execute(select(User.id).where(User.email == "mallory@example.com")).scalar_one()
        db.add(SubscriptionEntitlement(user_id=uid, status="active", expires_at=None))
        db.commit()
    for method, path in [("get", ""), ("patch", ""), ("post", "/discontinue"), ("delete", "")]:
        res = getattr(client, method)(f"{API}/{m['id']}{path}", headers=hm, **({"json": {}} if method == "patch" else {}))
        assert res.status_code == 404, (method, path)
    dose = {"scheduled_for": datetime.now(timezone.utc).isoformat(), "status": "taken"}
    assert client.put(f"{API}/{m['id']}/doses", headers=hm, json=dose).status_code == 404
    assert client.get(API, headers=hm).json() == []
