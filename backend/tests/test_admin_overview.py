"""Phase 4: the overview's figures must equal what's in the database, and respect permissions."""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.base import utcnow
from app.models.analytics import UserActivityDay
from app.models.billing import PaymentTransaction, SubscriptionEntitlement, WebhookEvent
from app.models.fitness import Workout
from app.models.hydration import HydrationEntry
from app.models.user import User
from app.services import activity
from app.services.admin_stats import mask_email, parse_range
from tests.conftest import auth, register
from tests.test_admin_auth import BASE, admin_headers

NOW = utcnow()
TODAY = NOW.date()


def at(days_ago: int, hour: int = 12) -> datetime:
    d = TODAY - timedelta(days=days_ago)
    return datetime(d.year, d.month, d.day, hour, tzinfo=timezone.utc)


def add_user(db, email, days_ago=0) -> User:
    u = User(email=email, password_hash="x", first_name=email.split("@")[0].title(), created_at=at(days_ago))
    db.add(u)
    db.flush()
    return u


def add_txn(db, user, *, amount, currency="USD", days_ago=0, status="succeeded", env="production",
            kind="initial_purchase", period_days=30):
    t = PaymentTransaction(
        user_id=user.id, provider="play_store", provider_transaction_id=uuid.uuid4().hex, product_id="premium_monthly",
        kind=kind, status=status, amount=Decimal(amount), currency=currency, purchased_at=at(days_ago),
        period_start=at(days_ago), period_end=at(days_ago) + timedelta(days=period_days), environment=env,
    )
    db.add(t)
    return t


def add_entitlement(db, user, *, status="active", store="play_store", will_renew=True, expires_in_days=20, env="production"):
    db.add(SubscriptionEntitlement(user_id=user.id, entitlement="premium", status=status, store=store,
                                   product_id="premium_monthly", will_renew=will_renew, environment=env,
                                   expires_at=None if expires_in_days is None else NOW + timedelta(days=expires_in_days)))


def add_hook(db, event_type, days_ago=0, env="PRODUCTION"):
    db.add(WebhookEvent(provider="revenuecat", event_id=uuid.uuid4().hex, event_type=event_type,
                        received_at=at(days_ago), status="processed", summary={"environment": env}))


@pytest.fixture
def seeded(db_factory):
    """5 users. 2 paying (USD + ZAR), 1 promotional, 1 lapsed, 1 free; plus noise that must be ignored."""
    db = db_factory()
    alice = add_user(db, "alice@example.com", days_ago=100)  # paying USD, monthly
    bongi = add_user(db, "bongi@example.com", days_ago=40)  # paying ZAR, monthly; one refund
    chris = add_user(db, "chris@example.com", days_ago=10)  # promotional premium
    dina = add_user(db, "dina@example.com", days_ago=5)  # expired premium, paid once long ago
    add_user(db, "eve@example.com", days_ago=0)  # free, joined today

    add_entitlement(db, alice)
    add_entitlement(db, bongi)
    add_entitlement(db, chris, store="promotional", will_renew=False, expires_in_days=None)
    add_entitlement(db, dina, status="expired", expires_in_days=-1)

    add_txn(db, alice, amount="11.00", days_ago=60)
    add_txn(db, alice, amount="11.00", days_ago=30, kind="renewal")
    add_txn(db, alice, amount="11.00", days_ago=2, kind="renewal")
    add_txn(db, bongi, amount="199.99", currency="ZAR", days_ago=20)
    add_txn(db, bongi, amount="199.99", currency="ZAR", days_ago=15, status="refunded")
    add_txn(db, dina, amount="11.00", days_ago=400)  # outside 30d and 12-month windows; still converted
    add_txn(db, chris, amount="11.00", days_ago=3, env="sandbox")  # sandbox: ignored everywhere

    add_hook(db, "CANCELLATION", days_ago=4)
    add_hook(db, "CANCELLATION", days_ago=45)  # outside range
    add_hook(db, "CANCELLATION", days_ago=1, env="SANDBOX")  # sandbox: ignored
    add_hook(db, "BILLING_ISSUE", days_ago=6)

    db.add_all([
        HydrationEntry(user_id=alice.id, client_id=uuid.uuid4(), volume_ml=250, consumed_at=at(1)),
        HydrationEntry(user_id=alice.id, client_id=uuid.uuid4(), volume_ml=250, consumed_at=at(2)),
        HydrationEntry(user_id=bongi.id, client_id=uuid.uuid4(), volume_ml=500, consumed_at=at(3)),
        HydrationEntry(user_id=bongi.id, client_id=uuid.uuid4(), volume_ml=500, consumed_at=at(3), deleted_at=NOW),
        HydrationEntry(user_id=chris.id, client_id=uuid.uuid4(), volume_ml=500, consumed_at=at(90)),  # outside
        Workout(user_id=alice.id, client_id=uuid.uuid4(), activity_type="running", source="gps", status="completed",
                started_at=at(1), distance_m=5000),
        Workout(user_id=alice.id, client_id=uuid.uuid4(), activity_type="walking", source="gps", status="discarded",
                started_at=at(1)),
    ])
    db.add_all([UserActivityDay(user_id=alice.id, day=TODAY - timedelta(days=d)) for d in (0, 1, 2)])
    db.add(UserActivityDay(user_id=bongi.id, day=TODAY - timedelta(days=1)))
    db.commit()
    db.close()


def get(client, h, **params):
    return client.get(f"{BASE}/overview", headers=h, params=params)


def test_overview_matches_database(client, db_factory, seeded):
    res = get(client, admin_headers(client, db_factory, "owner"))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["range"] == {"from": (TODAY - timedelta(days=29)).isoformat(), "to": TODAY.isoformat()}

    u = body["users"]
    assert u["total"] == 5
    assert u["new_in_range"] == 3  # chris, dina, eve; alice (100 days) and bongi (40) are older
    assert u["premium"] == 3 and u["premium_promotional"] == 1  # alice, bongi, chris; dina expired
    assert u["free"] == 2
    assert u["active_in_range"] == 2
    assert u["activity_tracked_since"] == (TODAY - timedelta(days=2)).isoformat()

    s = body["subscriptions"]
    assert s["converted_users"] == 3  # alice, bongi (incl. refunded), dina; not sandbox chris
    assert s["conversion_rate"] == 0.6
    assert s["cancellations_in_range"] == 1
    assert s["failed_payments_in_range"] == 1

    rev = {r["currency"]: r for r in body["revenue"]["by_currency"]}
    assert set(rev) == {"USD", "ZAR"}
    assert rev["USD"]["total"] == "44.00"  # 3 × 11 alice + 11 dina; refund & sandbox excluded
    assert rev["USD"]["in_range"] == "11.00"  # only 2 days ago: the range is today + 29 days, so 30 days ago is out
    assert rev["ZAR"]["total"] == "199.99" and rev["ZAR"]["in_range"] == "199.99"
    assert rev["USD"]["mrr"] == "11.16"  # 11 × 30.4375 / 30
    assert rev["ZAR"]["mrr"] == "202.91"
    assert body["revenue"]["sandbox_transactions_excluded"] == 1

    usage = {f["feature"]: f for f in body["feature_usage"]}
    assert (usage["water"]["users"], usage["water"]["records"]) == (2, 3)  # deleted & out-of-range excluded
    assert (usage["fitness"]["users"], usage["fitness"]["records"]) == (1, 1)
    assert (usage["medication"]["users"], usage["medication"]["records"]) == (0, 0)


def test_series(client, db_factory, seeded):
    body = get(client, admin_headers(client, db_factory), **{"from": (TODAY - timedelta(days=6)).isoformat()}).json()
    growth = body["series"]["user_growth"]
    assert len(growth) == 7
    assert growth[0]["total_users"] == 3  # alice, bongi, chris joined before the range... plus dina on day -5
    assert growth[-1]["total_users"] == 5 and growth[-1]["new_users"] == 1
    assert sum(p["new_users"] for p in growth) == 2
    active = {p["date"]: p["active_users"] for p in body["series"]["active_users"]}
    assert active[(TODAY - timedelta(days=1)).isoformat()] == 2 and active[TODAY.isoformat()] == 1

    months = body["series"]["revenue_monthly"]
    assert len(months) == 12 and months[-1]["month"] == f"{TODAY:%Y-%m}"
    usd_total = sum(Decimal(m["amounts"].get("USD", "0")) for m in months)
    assert usd_total == Decimal("33.00")  # dina's payment (400 days ago) is outside the 12 months
    conv = body["series"]["conversion_monthly"]
    assert conv[-1]["registered_users"] == 5 and conv[-1]["converted_users"] == 3


def test_recent_activity_is_masked_and_permission_aware(client, db_factory, seeded):
    owner = get(client, admin_headers(client, db_factory, "owner")).json()["recent_activity"]
    kinds = {i["type"] for i in owner}
    assert {"registration", "subscription", "payment", "refund", "cancellation", "payment_failed", "admin_action"} <= kinds
    regs = [i for i in owner if i["type"] == "registration"]
    assert all("@" in i["detail"] and "•••" in i["detail"] for i in regs)
    assert not any("alice@example.com" in str(i) for i in owner)
    assert [i["at"] for i in owner] == sorted((i["at"] for i in owner), reverse=True)


def test_roles_without_payments_get_no_revenue(client, db_factory, seeded):
    body = get(client, admin_headers(client, db_factory, "support")).json()
    assert body["revenue"] is None and body["series"]["revenue_monthly"] is None
    kinds = {i["type"] for i in body["recent_activity"]}
    assert kinds.isdisjoint({"payment", "refund", "payment_failed", "admin_action"})
    assert not any("USD" in str(i) or "ZAR" in str(i) for i in body["recent_activity"])


def test_finance_sees_revenue(client, db_factory, seeded):
    body = get(client, admin_headers(client, db_factory, "finance")).json()
    assert body["revenue"]["by_currency"]


def test_overview_requires_admin(client, db_factory):
    assert client.get(f"{BASE}/overview").status_code == 401
    session = register(client)
    assert client.get(f"{BASE}/overview", headers=auth(session["access_token"])).status_code == 401


def test_empty_database_gives_zeros_not_errors(client, db_factory):
    body = get(client, admin_headers(client, db_factory)).json()
    assert body["users"]["total"] == 0 and body["subscriptions"]["conversion_rate"] is None
    assert body["revenue"]["by_currency"] == []
    assert body["users"]["activity_tracked_since"] is None


@pytest.mark.parametrize("params,msg", [
    ({"from": "2026-05-10", "to": "2026-05-01"}, "on or before"),
    ({"to": (TODAY + timedelta(days=1)).isoformat()}, "future"),
    ({"from": (TODAY - timedelta(days=400)).isoformat()}, "at most 366"),
])
def test_invalid_ranges_are_rejected(client, db_factory, params, msg):
    res = get(client, admin_headers(client, db_factory), **params)
    assert res.status_code == 422 and msg in res.json()["error"]["message"]
    assert get(client, admin_headers(client, db_factory, "admin"), **{"from": "bad"}).status_code == 422


def test_parse_range_defaults_to_30_days():
    r = parse_range(None, None)
    assert (r.end - r.start).days == 29 and r.end == TODAY
    assert parse_range(date(2026, 1, 1), date(2026, 1, 1)).days() == [date(2026, 1, 1)]


def test_mask_email():
    assert mask_email("alice@example.com") == "a•••@example.com"
    assert mask_email("broken") == "•••"


# ---------- activity tracking (written by the app's auth dependency) ----------

def test_app_requests_record_one_activity_row_per_day(client, db_factory):
    activity.forget()
    session = register(client)
    h = auth(session["access_token"])
    for _ in range(3):
        assert client.get("/api/v1/me", headers=h).status_code == 200
    activity.forget()  # a second worker process would also try: still one row
    client.get("/api/v1/me", headers=h)
    db = db_factory()
    rows = db.execute(select(UserActivityDay)).scalars().all()
    assert len(rows) == 1 and rows[0].day == TODAY
    db.close()


def test_failed_auth_records_nothing(client, db_factory):
    client.get("/api/v1/me", headers=auth("not-a-token"))
    db = db_factory()
    assert db.execute(select(UserActivityDay)).first() is None
    db.close()
