"""Subscriptions. RevenueCat is replaced by a fake: tests never call the real API."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import PremiumUser
from app.core.config import get_settings
from app.main import app
from app.models.billing import PaymentTransaction, SubscriptionEntitlement, WebhookEvent
from app.services import revenuecat
from app.services.revenuecat import RevenueCatError, derive_entitlement

API = "/api/v1"
SECRET = "whsec-test-test-test-test-test-test-test"
NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def subscriber(expires: datetime | None, **sub_fields) -> dict:
    """Shape of GET /v1/subscribers/{id} → .subscriber"""
    return {
        "entitlements": {"premium": {
            "expires_date": iso(expires) if expires else None,
            "product_identifier": "premium_monthly",
            "purchase_date": iso(NOW - timedelta(days=3)),
            "grace_period_expires_date": sub_fields.pop("grace", None),
        }},
        "subscriptions": {"premium_monthly": {
            "store": "app_store", "is_sandbox": False, "original_transaction_id": "1000",
            "purchase_date": iso(NOW - timedelta(days=3)), **sub_fields,
        }},
    }


class FakeRevenueCat:
    def __init__(self):
        self.subscribers: dict[str, dict] = {}
        self.calls: list[str] = []
        self.down = False

    def get_subscriber(self, app_user_id: str) -> dict:
        self.calls.append(app_user_id)
        if self.down:
            raise RevenueCatError("down")
        return self.subscribers.get(app_user_id, {"entitlements": {}, "subscriptions": {}})


@pytest.fixture
def rc(monkeypatch):
    fake = FakeRevenueCat()
    monkeypatch.setattr(revenuecat, "get_client", lambda: fake)
    monkeypatch.setattr(get_settings(), "revenuecat_webhook_auth", SECRET)
    return fake


def event(user_id, type_="INITIAL_PURCHASE", **kw) -> dict:
    return {"api_version": "1.0", "event": {
        "id": kw.pop("id", str(uuid.uuid4())), "type": type_, "app_user_id": str(user_id),
        "product_id": "premium_monthly", "store": "APP_STORE", "environment": "PRODUCTION",
        "transaction_id": kw.pop("transaction_id", "2000"), "original_transaction_id": "1000",
        "price_in_purchased_currency": 11.0, "currency": "USD",
        "purchased_at_ms": int((datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp() * 1000),
        "expiration_at_ms": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp() * 1000),
        **kw,
    }}


def hook(client, body, auth=SECRET):
    return client.post(f"{API}/billing/webhooks/revenuecat", json=body, headers={"Authorization": auth} if auth else {})


def user_id(client, h) -> str:
    return client.get(f"{API}/me", headers=h).json()["id"]


# ---------------------------------------------------------------- status derivation (pure)

def test_derive_active_cancelled_grace_billing_issue_expired_refunded():
    d = lambda s: derive_entitlement(s, "premium", NOW)  # noqa: E731
    future, past = NOW + timedelta(days=10), NOW - timedelta(days=1)
    assert d(subscriber(future)).status == "active" and d(subscriber(future)).will_renew
    c = d(subscriber(future, unsubscribe_detected_at=iso(past)))
    assert c.status == "cancelled" and not c.will_renew  # still paid up until expiry
    g = d(subscriber(past, billing_issues_detected_at=iso(past), grace=iso(NOW + timedelta(days=5))))
    assert g.status == "grace_period" and g.expires_at == NOW + timedelta(days=5)
    assert d(subscriber(past, billing_issues_detected_at=iso(past))).status == "billing_issue"
    assert d(subscriber(past)).status == "expired"
    assert d(subscriber(future, refunded_at=iso(past))).status == "refunded"
    assert d(subscriber(None)).status == "active"  # lifetime / promotional
    assert d({"entitlements": {}, "subscriptions": {}}) is None
    assert d(subscriber(future, is_sandbox=True)).environment == "sandbox"


# ---------------------------------------------------------------- webhook security & idempotency

def test_webhook_rejects_missing_or_wrong_secret(client, rc, verified):
    h, _ = verified
    body = event(user_id(client, h))
    assert hook(client, body, auth=None).status_code == 401
    assert hook(client, body, auth="wrong").status_code == 401
    assert rc.calls == []


def test_webhook_refuses_when_secret_not_configured(client, rc, monkeypatch, verified):
    monkeypatch.setattr(get_settings(), "revenuecat_webhook_auth", None)
    assert hook(client, event(uuid.uuid4()), auth="anything").status_code == 503


def test_purchase_webhook_grants_premium_from_refetched_state(client, rc, verified, db_factory):
    h, _ = verified
    uid = user_id(client, h)
    rc.subscribers[uid] = subscriber(datetime.now(timezone.utc) + timedelta(days=30))
    res = hook(client, event(uid), auth=f"Bearer {SECRET}")  # "Bearer x" and "x" both accepted
    assert res.status_code == 200 and res.json()["status"] == "processed"
    assert rc.calls == [uid]
    assert client.get(f"{API}/me", headers=h).json()["plan"] == "premium"
    txns = client.get(f"{API}/billing/transactions", headers=h).json()
    assert len(txns) == 1 and txns[0]["amount"] == "11.0000" and txns[0]["currency"] == "USD"
    assert txns[0]["receipt_number"].startswith("HL-")


def test_event_alone_never_grants_premium(client, rc, verified):
    """A forged-but-authenticated or stale event can't grant access: RevenueCat's API is the truth."""
    h, _ = verified
    uid = user_id(client, h)  # RevenueCat says: no entitlement
    assert hook(client, event(uid)).status_code == 200
    assert client.get(f"{API}/me", headers=h).json()["plan"] == "free"


def test_duplicate_webhook_is_processed_once(client, rc, verified, db_factory):
    h, _ = verified
    uid = user_id(client, h)
    rc.subscribers[uid] = subscriber(datetime.now(timezone.utc) + timedelta(days=30))
    body = event(uid, id="evt-1")
    assert hook(client, body).json()["status"] == "processed"
    assert hook(client, body).json()["status"] == "duplicate"
    with db_factory() as db:
        assert len(db.execute(select(PaymentTransaction)).scalars().all()) == 1
        assert len(db.execute(select(WebhookEvent)).scalars().all()) == 1
    assert rc.calls == [uid]


def test_same_transaction_in_two_events_is_recorded_once(client, rc, verified, db_factory):
    h, _ = verified
    uid = user_id(client, h)
    hook(client, event(uid, transaction_id="t-9"))
    hook(client, event(uid, transaction_id="t-9"))
    with db_factory() as db:
        assert len(db.execute(select(PaymentTransaction)).scalars().all()) == 1


def test_provider_outage_returns_503_then_retry_succeeds(client, rc, verified, db_factory):
    h, _ = verified
    uid = user_id(client, h)
    rc.subscribers[uid] = subscriber(datetime.now(timezone.utc) + timedelta(days=30))
    rc.down = True
    body = event(uid, id="evt-retry")
    assert hook(client, body).status_code == 503  # RevenueCat will retry
    with db_factory() as db:
        assert db.execute(select(WebhookEvent)).scalar_one().status == "failed"
    rc.down = False
    assert hook(client, body).json()["status"] == "processed"
    assert client.get(f"{API}/me", headers=h).json()["plan"] == "premium"
    with db_factory() as db:
        assert len(db.execute(select(PaymentTransaction)).scalars().all()) == 1


def test_unknown_users_and_test_events_are_ignored(client, rc, verified):
    assert hook(client, event("$RCAnonymousID:abc")).json()["status"] == "ignored"
    assert hook(client, event(uuid.uuid4())).json()["status"] == "ignored"
    h, _ = verified
    assert hook(client, event(user_id(client, h), type_="TEST")).json()["status"] == "ignored"
    assert rc.calls == []


def test_expiration_and_refund_revoke_premium(client, rc, verified, db_factory):
    h, _ = verified
    uid = user_id(client, h)
    now = datetime.now(timezone.utc)
    rc.subscribers[uid] = subscriber(now + timedelta(days=30))
    hook(client, event(uid, transaction_id="t-1"))
    assert client.get(f"{API}/me", headers=h).json()["plan"] == "premium"

    rc.subscribers[uid] = subscriber(now + timedelta(days=30), refunded_at=iso(now))
    hook(client, event(uid, type_="CANCELLATION", transaction_id="t-1", cancel_reason="CUSTOMER_SUPPORT"))
    assert client.get(f"{API}/me", headers=h).json()["plan"] == "free"
    assert client.get(f"{API}/billing/status", headers=h).json()["entitlement"]["status"] == "refunded"
    txn = client.get(f"{API}/billing/transactions", headers=h).json()[0]
    assert txn["status"] == "refunded" and txn["amount"] == "11.0000"  # amount is never rewritten


def test_grace_period_keeps_premium_billing_issue_does_not(client, rc, verified):
    h, _ = verified
    uid = user_id(client, h)
    now = datetime.now(timezone.utc)
    rc.subscribers[uid] = subscriber(now - timedelta(hours=1), billing_issues_detected_at=iso(now),
                                     grace=iso(now + timedelta(days=3)))
    hook(client, event(uid, type_="BILLING_ISSUE"))
    assert client.get(f"{API}/me", headers=h).json()["plan"] == "premium"
    rc.subscribers[uid] = subscriber(now - timedelta(hours=1), billing_issues_detected_at=iso(now))
    hook(client, event(uid, type_="EXPIRATION"))
    assert client.get(f"{API}/me", headers=h).json()["plan"] == "free"


def test_transfer_updates_both_accounts(client, rc, verified):
    from tests.conftest import auth, last_code, register

    h, _ = verified
    a = user_id(client, h)
    s = register(client, email="bob@example.com")
    hb = auth(s["access_token"])
    client.post(f"{API}/auth/verify-email", json={"code": last_code("bob@example.com")}, headers=hb)
    b = s["user"]["id"]
    rc.subscribers[a] = subscriber(datetime.now(timezone.utc) + timedelta(days=30))
    hook(client, event(a))
    assert client.get(f"{API}/me", headers=h).json()["plan"] == "premium"
    rc.subscribers[b], rc.subscribers[a] = rc.subscribers[a], {"entitlements": {}, "subscriptions": {}}
    body = event(a, type_="TRANSFER")
    body["event"].pop("app_user_id")
    body["event"].update(transferred_from=[a], transferred_to=[b])
    assert hook(client, body).json()["status"] == "processed"
    assert client.get(f"{API}/me", headers=h).json()["plan"] == "free"
    assert client.get(f"{API}/me", headers=hb).json()["plan"] == "premium"


# ---------------------------------------------------------------- client sync, receipts, gating

def test_sync_ignores_client_claims_and_asks_revenuecat(client, rc, verified):
    h, _ = verified
    uid = user_id(client, h)
    res = client.post(f"{API}/billing/sync", headers=h, json={"plan": "premium", "status": "active"})
    assert res.status_code == 200 and res.json()["plan"] == "free"
    rc.subscribers[uid] = subscriber(datetime.now(timezone.utc) + timedelta(days=30))
    assert client.post(f"{API}/billing/sync", headers=h).json()["plan"] == "premium"
    rc.down = True
    assert client.post(f"{API}/billing/sync", headers=h).status_code == 503


def test_receipt_pdf_and_ownership(client, rc, verified):
    from tests.conftest import auth, register

    h, _ = verified
    uid = user_id(client, h)
    hook(client, event(uid))
    txn = client.get(f"{API}/billing/transactions", headers=h).json()[0]
    res = client.get(f"{API}/billing/transactions/{txn['id']}/receipt.pdf", headers=h)
    assert res.status_code == 200 and res.headers["content-type"] == "application/pdf"
    assert res.content.startswith(b"%PDF") and txn["receipt_number"] in res.headers["content-disposition"]
    other = auth(register(client, email="eve@example.com")["access_token"])
    assert client.get(f"{API}/billing/transactions/{txn['id']}/receipt.pdf", headers=other).status_code == 404
    assert client.get(f"{API}/billing/transactions", headers=other).json() == []


def test_require_premium_dependency(client, rc, verified, db_factory):
    router = APIRouter()

    @router.get("/_premium_probe")
    def probe(user: PremiumUser):
        return {"ok": True}

    app.include_router(router)
    h, _ = verified
    res = client.get("/_premium_probe", headers=h)
    assert res.status_code == 402 and res.json()["error"]["code"] == "premium_required"
    with db_factory() as db:  # an expired entitlement row must not unlock anything
        db.add(SubscriptionEntitlement(user_id=uuid.UUID(user_id(client, h)), status="active",
                                       expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
        db.commit()
    assert client.get("/_premium_probe", headers=h).status_code == 402
    with db_factory() as db:
        ent = db.execute(select(SubscriptionEntitlement)).scalar_one()
        ent.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
        db.commit()
    assert client.get("/_premium_probe", headers=h).json() == {"ok": True}
