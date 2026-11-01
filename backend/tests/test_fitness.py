import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.billing import SubscriptionEntitlement
from app.services import geo
from tests.conftest import auth, last_code, register

API = "/api/v1"
M_PER_DEG_LAT = 2 * 3.141592653589793 * geo.EARTH_RADIUS_M / 360  # ≈ 111,195 m


# ---------------------------------------------------------------- geo (pure)

def track(n: int, step_m: float, dt_s: float, start: datetime, segment: int = 0, seq0: int = 0, lat0: float = -26.2):
    """A straight walk north: n fixes, step_m apart, every dt_s seconds."""
    return [geo.Fix(seq=seq0 + i, segment=segment, recorded_at=start + timedelta(seconds=dt_s * i),
                    lat=lat0 + (step_m * i) / M_PER_DEG_LAT, lon=28.04, accuracy_m=5) for i in range(n)]


def test_haversine_known_distance():
    assert abs(geo.haversine_m(0, 0, 1, 0) - M_PER_DEG_LAT) < 1
    # Johannesburg → Pretoria ≈ 54–56 km great-circle
    assert 53_000 < geo.haversine_m(-26.2041, 28.0473, -25.7479, 28.2293) < 57_000


def test_filters_low_accuracy_jumps_and_jitter():
    t0 = datetime(2026, 11, 1, 6, 0, tzinfo=timezone.utc)
    fixes = track(11, 7, 5, t0)  # 70 m in 50 s (1.4 m/s walking)
    fixes[3].accuracy_m = 80  # poor fix
    fixes[6].lat += 0.01  # ~1.1 km teleport
    fixes.append(geo.Fix(seq=99, segment=0, recorded_at=t0 + timedelta(seconds=60),
                         lat=fixes[10].lat + 0.5 / M_PER_DEG_LAT, lon=28.04, accuracy_m=5))  # 0.5 m jitter
    geo.filter_fixes(fixes, "walking")
    assert [f.seq for f in fixes if not f.accepted] == [3, 6, 99]
    assert abs(geo.route_distance_m(fixes) - 70) < 0.5


def test_distance_never_bridges_a_pause():
    t0 = datetime(2026, 11, 1, 6, 0, tzinfo=timezone.utc)
    a = track(5, 7, 5, t0)  # 28 m
    b = track(5, 7, 5, t0 + timedelta(minutes=10), segment=1, seq0=5, lat0=-26.19)  # resumes ~1.1 km away
    fixes = geo.filter_fixes(a + b, "walking")
    assert all(f.accepted for f in fixes)
    assert abs(geo.route_distance_m(fixes) - 56) < 0.5


def test_calories_are_an_estimate_or_nothing():
    assert geo.calories_estimate("walking", 3600, 70) == 245.0  # 3.5 MET × 70 kg × 1 h
    assert geo.calories_estimate("running", 1800, 70) == 343.0
    assert geo.calories_estimate("walking", 3600, None) is None  # no weight → no guess
    assert geo.pace_s_per_km(1000, 600) == 600


# ---------------------------------------------------------------- API

@pytest.fixture
def premium(client, verified, db_factory):
    h, s = verified
    with db_factory() as db:
        db.add(SubscriptionEntitlement(user_id=uuid.UUID(s["user"]["id"]), status="active", expires_at=None))
        db.commit()
    return h


def now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def points(n, step_m, dt_s, start, segment=0, seq0=0, lat0=-26.2):
    return [{"seq": seq0 + i, "segment": segment, "recorded_at": (start + timedelta(seconds=dt_s * i)).isoformat(),
             "lat": lat0 + step_m * i / M_PER_DEG_LAT, "lon": 28.04, "accuracy_m": 5} for i in range(n)]


def start_workout(client, h, minutes_ago=20, activity="walking", cid=None):
    body = {"client_id": str(cid or uuid.uuid4()), "activity_type": activity,
            "started_at": (now() - timedelta(minutes=minutes_ago)).isoformat()}
    return client.post(f"{API}/workouts", headers=h, json=body)


def test_free_users_can_list_and_delete_but_not_record(client, verified):
    h, _ = verified
    assert start_workout(client, h).status_code == 402
    assert client.get(f"{API}/workouts", headers=h).json() == []
    assert client.get(f"{API}/fitness/summary", headers=h).status_code == 402
    assert client.get(f"{API}/workouts").status_code == 401


def test_gps_workout_lifecycle_server_computes_distance(client, premium):
    h = premium
    client.put(f"{API}/me/fitness-profile", headers=h, json={"body_weight_kg": 70})
    cid = uuid.uuid4()
    w = start_workout(client, h, cid=cid)
    assert w.status_code == 201
    assert start_workout(client, h, cid=cid).json()["id"] == w.json()["id"]  # idempotent start
    wid = w.json()["id"]
    t0 = now() - timedelta(minutes=19)
    batch = points(101, 7, 5, t0)  # 700 m
    r = client.post(f"{API}/workouts/{wid}/points", headers=h, json={"points": batch[:60]})
    assert r.json()["added"] == 60
    r = client.post(f"{API}/workouts/{wid}/points", headers=h, json={"points": batch[40:]})  # overlapping retry
    assert r.json()["added"] == 41 and abs(r.json()["distance_m"] - 700) < 1
    done = client.post(f"{API}/workouts/{wid}/finish", headers=h, json={
        "ended_at": now().isoformat(), "active_duration_s": 600, "steps": 900})
    body = done.json()
    assert done.status_code == 200 and body["status"] == "completed"
    assert abs(body["distance_m"] - 700) < 1 and body["point_count"] == 101
    assert body["calories_kcal_estimate"] == 40.8  # 3.5 × 70 × 600/3600
    assert round(body["pace_s_per_km"]) == 857
    # retrying finish is harmless; uploading after finish is refused
    assert client.post(f"{API}/workouts/{wid}/finish", headers=h,
                       json={"ended_at": now().isoformat(), "active_duration_s": 600}).status_code == 200
    assert client.post(f"{API}/workouts/{wid}/points", headers=h, json={"points": batch[:1]}).status_code == 409
    detail = client.get(f"{API}/workouts/{wid}", headers=h).json()
    assert len(detail["route"]) == 101
    assert [w["id"] for w in client.get(f"{API}/workouts", headers=h).json()] == [wid]


def test_client_cannot_inflate_distance_or_duration(client, premium):
    h = premium
    wid = start_workout(client, h, minutes_ago=10).json()["id"]
    t0 = now() - timedelta(minutes=9)
    jumpy = points(5, 7, 5, t0)
    jumpy[2]["lat"] += 0.05  # 5.5 km teleport
    client.post(f"{API}/workouts/{wid}/points", headers=h, json={"points": jumpy})
    done = client.post(f"{API}/workouts/{wid}/finish", headers=h,
                       json={"ended_at": now().isoformat(), "active_duration_s": 86_000}).json()
    assert done["distance_m"] < 30
    assert done["active_duration_s"] <= 600  # capped to wall-clock time
    assert done["calories_kcal_estimate"] is None  # no weight on file


def test_points_outside_the_workout_window_are_ignored(client, premium):
    h = premium
    wid = start_workout(client, h, minutes_ago=5).json()["id"]
    stale = points(3, 7, 5, now() - timedelta(hours=3))
    assert client.post(f"{API}/workouts/{wid}/points", headers=h, json={"points": stale}).json()["added"] == 0
    bad = [{"seq": 0, "recorded_at": now().isoformat(), "lat": 95, "lon": 0}]
    assert client.post(f"{API}/workouts/{wid}/points", headers=h, json={"points": bad}).status_code == 422


def test_discarded_workouts_are_not_listed(client, premium):
    h = premium
    wid = start_workout(client, h).json()["id"]
    assert client.post(f"{API}/workouts/{wid}/discard", headers=h).json()["status"] == "discarded"
    assert client.get(f"{API}/workouts", headers=h).json() == []
    assert client.post(f"{API}/workouts/{wid}/finish", headers=h,
                       json={"ended_at": now().isoformat(), "active_duration_s": 60}).status_code == 409


def test_manual_workout_and_validation(client, premium):
    h = premium
    body = {"client_id": str(uuid.uuid4()), "activity_type": "running",
            "started_at": (now() - timedelta(hours=2)).isoformat(), "active_duration_s": 1800, "distance_m": 5000}
    r = client.post(f"{API}/workouts/manual", headers=h, json=body)
    assert r.status_code == 201 and r.json()["source"] == "manual" and r.json()["distance_m"] == 5000
    assert client.post(f"{API}/workouts/manual", headers=h, json=body).status_code == 200  # idempotent
    future = {**body, "client_id": str(uuid.uuid4()), "started_at": (now() - timedelta(minutes=5)).isoformat()}
    assert client.post(f"{API}/workouts/manual", headers=h, json=future).json()["error"]["code"] == "future_timestamp"
    assert client.post(f"{API}/workouts/manual", headers=h, json={**body, "activity_type": "flying"}).status_code == 422


def test_health_import_requires_connection_and_dedups(client, premium):
    h = premium
    rec = {"external_id": "hc-123", "activity_type": "walking",
           "started_at": (now() - timedelta(hours=3)).isoformat(),
           "ended_at": (now() - timedelta(hours=2, minutes=30)).isoformat(), "distance_m": 2500, "steps": 3200}
    body = {"provider": "health_connect", "records": [rec]}
    assert client.post(f"{API}/health/import", headers=h, json=body).json()["error"]["code"] == "not_connected"
    client.put(f"{API}/health/connections/health_connect", headers=h, json={"granted_data_types": ["exercise", "steps"]})
    assert client.post(f"{API}/health/import", headers=h, json=body).json() == {"imported": 1, "updated": 0, "skipped": 0}
    again = client.post(f"{API}/health/import", headers=h, json={**body, "records": [{**rec, "distance_m": 2600}]})
    assert again.json() == {"imported": 0, "updated": 1, "skipped": 0}
    ws = client.get(f"{API}/workouts", headers=h).json()
    assert len(ws) == 1 and ws[0]["distance_m"] == 2600 and ws[0]["source"] == "health_connect"
    conns = client.get(f"{API}/health/connections", headers=h).json()
    assert conns[0]["active"] and conns[0]["last_synced_at"]
    # disconnect + delete imported data
    client.delete(f"{API}/health/connections/health_connect", headers=h, params={"delete_imported": "true"})
    assert client.get(f"{API}/workouts", headers=h).json() == []
    assert client.post(f"{API}/health/import", headers=h, json=body).status_code == 409


def test_goals_and_weekly_summary(client, premium):
    h = premium
    g = client.post(f"{API}/fitness/goals", headers=h, json={"metric": "distance_km", "period": "weekly", "target_value": 10})
    assert g.status_code == 201 and g.json()["current_value"] == 0
    client.post(f"{API}/workouts/manual", headers=h, json={
        "client_id": str(uuid.uuid4()), "activity_type": "walking",
        "started_at": (now() - timedelta(minutes=70)).isoformat(), "active_duration_s": 3600, "distance_m": 4000})
    s = client.get(f"{API}/fitness/summary", headers=h).json()
    assert s["workouts"] == 1 and s["distance_km"] == 4.0 and s["active_minutes"] == 60.0
    assert s["goals"][0]["progress"] == 0.4
    assert client.delete(f"{API}/fitness/goals/{g.json()['id']}", headers=h).status_code == 204
    assert client.get(f"{API}/fitness/goals", headers=h).json() == []
    assert client.post(f"{API}/fitness/goals", headers=h,
                       json={"metric": "distance_km", "period": "weekly", "target_value": 0}).status_code == 422


def test_workouts_are_private(client, premium):
    wid = start_workout(client, premium).json()["id"]
    s = register(client, email="eve@example.com")
    he = auth(s["access_token"])
    client.post(f"{API}/auth/verify-email", json={"code": last_code("eve@example.com")}, headers=he)
    assert client.get(f"{API}/workouts/{wid}", headers=he).status_code == 404
    assert client.delete(f"{API}/workouts/{wid}", headers=he).status_code == 404
    assert client.delete(f"{API}/workouts/{wid}", headers=premium).status_code == 204


def test_fitness_profile_weight_is_optional(client, verified):
    h, _ = verified
    assert client.get(f"{API}/me/fitness-profile", headers=h).json() == {"body_weight_kg": None}
    assert client.put(f"{API}/me/fitness-profile", headers=h, json={"body_weight_kg": 5}).status_code == 422
    assert client.put(f"{API}/me/fitness-profile", headers=h, json={"body_weight_kg": 68.5}).json()["body_weight_kg"] == 68.5
    assert client.put(f"{API}/me/fitness-profile", headers=h, json={"body_weight_kg": None}).json()["body_weight_kg"] is None
