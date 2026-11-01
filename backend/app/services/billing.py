"""Subscriptions: webhook ingestion, entitlement sync and the payment ledger.

Flow for every change (purchase, renewal, cancellation, refund, billing issue, transfer ...):
  1. RevenueCat calls our webhook (authenticated with a shared secret header).
  2. The event is recorded once (idempotent on its id) — retries and duplicates are harmless.
  3. Purchase events add an immutable row to the payment ledger; refunds only flip its status.
  4. Entitlement is NOT taken from the event: we re-fetch the subscriber from RevenueCat's API and
     store what it says. Out-of-order or replayed events therefore can't grant or revoke access.
"""

import logging
import secrets
import uuid
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import utcnow
from app.models.billing import PaymentTransaction, SubscriptionEntitlement, WebhookEvent
from app.models.user import User
from app.services import revenuecat
from app.services.revenuecat import EntitlementState, RevenueCatError, derive_entitlement, normalise_store, parse_ts

logger = logging.getLogger("app.billing")

PROVIDER = "revenuecat"
PURCHASE_KINDS = {
    "INITIAL_PURCHASE": "initial_purchase",
    "RENEWAL": "renewal",
    "PRODUCT_CHANGE": "product_change",
    "NON_RENEWING_PURCHASE": "initial_purchase",
}
LEDGER_STORES = {"app_store", "play_store", "stripe", "promotional"}  # matches the CHECK constraint


# ---------------------------------------------------------------- entitlement sync

def _apply_state(db: Session, user_id: uuid.UUID, state: EntitlementState | None) -> SubscriptionEntitlement | None:
    name = get_settings().revenuecat_premium_entitlement
    row = db.execute(select(SubscriptionEntitlement).where(
        SubscriptionEntitlement.user_id == user_id, SubscriptionEntitlement.entitlement == name,
    )).scalar_one_or_none()
    if state is None:
        if row is not None:  # RevenueCat no longer lists it (e.g. transferred away)
            row.status, row.will_renew, row.last_verified_at = "expired", False, utcnow()
            row.expires_at = row.expires_at or utcnow()
        return row
    if row is None:
        row = SubscriptionEntitlement(user_id=user_id, entitlement=name, status=state.status)
        db.add(row)
    row.status = state.status
    row.product_id = state.product_id
    row.store = state.store
    row.expires_at = state.expires_at
    row.current_period_start = state.current_period_start
    row.will_renew = state.will_renew
    row.environment = state.environment
    row.original_transaction_id = state.original_transaction_id
    row.last_verified_at = utcnow()
    return row


def sync_user(db: Session, user_id: uuid.UUID) -> SubscriptionEntitlement | None:
    """Fetch the truth from RevenueCat and store it. Raises RevenueCatError if unavailable."""
    subscriber = revenuecat.get_client().get_subscriber(str(user_id))
    state = derive_entitlement(subscriber, get_settings().revenuecat_premium_entitlement, utcnow())
    for attempt in range(2):
        row = _apply_state(db, user_id, state)
        try:
            db.commit()
            return row
        except IntegrityError:  # a concurrent sync inserted the row first; retry as an update
            db.rollback()
            if attempt:
                raise
    return None


def get_entitlement(db: Session, user_id: uuid.UUID) -> SubscriptionEntitlement | None:
    return db.execute(select(SubscriptionEntitlement).where(
        SubscriptionEntitlement.user_id == user_id,
        SubscriptionEntitlement.entitlement == get_settings().revenuecat_premium_entitlement,
    )).scalar_one_or_none()


# ---------------------------------------------------------------- webhook

def check_webhook_auth(header: str | None) -> None:
    expected = get_settings().revenuecat_webhook_auth
    if not expected:
        # Never accept unauthenticated billing events, even in development.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            {"code": "webhook_not_configured", "message": "Webhook secret is not configured."})
    supplied = (header or "").strip()
    if supplied.lower().startswith("bearer "):
        supplied = supplied[7:].strip()
    if not secrets.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, {"code": "invalid_signature", "message": "Unauthorized."})


def _user_ids(db: Session, event: dict) -> list[uuid.UUID]:
    """Our app_user_id is the user's UUID. TRANSFER events name both sides instead."""
    if event.get("type") == "TRANSFER":
        candidates = list(event.get("transferred_from") or []) + list(event.get("transferred_to") or [])
    else:
        candidates = [event.get("app_user_id"), event.get("original_app_user_id"), *(event.get("aliases") or [])]
    found: list[uuid.UUID] = []
    for c in candidates:
        try:
            uid = uuid.UUID(str(c))
        except ValueError:
            continue  # anonymous RevenueCat ids ($RCAnonymousID:...) never map to our users
        if uid not in found and db.get(User, uid) is not None:
            found.append(uid)
        if event.get("type") != "TRANSFER" and found:
            break
    return found


def _decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _receipt_number() -> str:
    return f"HL-{utcnow():%Y%m%d}-{secrets.token_hex(4).upper()}"


def _record_transaction(db: Session, user_id: uuid.UUID, event: dict) -> None:
    kind = PURCHASE_KINDS.get(event.get("type", ""))
    store = normalise_store(event.get("store"))
    txn_id = event.get("transaction_id")
    if not kind or store not in LEDGER_STORES or not txn_id:
        return
    exists = db.execute(select(PaymentTransaction.id).where(
        PaymentTransaction.provider == store, PaymentTransaction.provider_transaction_id == txn_id,
    )).first()
    if exists:
        return
    amount = _decimal(event.get("price_in_purchased_currency"))
    succeeded = amount is not None and amount >= 0
    db.add(PaymentTransaction(
        user_id=user_id,
        provider=store,
        provider_transaction_id=txn_id,
        original_transaction_id=event.get("original_transaction_id"),
        product_id=event.get("product_id") or "unknown",
        kind=kind,
        status="succeeded" if succeeded else "pending",
        amount=amount,
        currency=(event.get("currency") or None) and str(event["currency"]).upper()[:3],
        tax_amount=None,  # RevenueCat doesn't give a tax amount; we never invent one
        purchased_at=parse_ts(event.get("purchased_at_ms")) or utcnow(),
        period_start=parse_ts(event.get("purchased_at_ms")),
        period_end=parse_ts(event.get("expiration_at_ms")),
        environment="sandbox" if str(event.get("environment", "")).upper() == "SANDBOX" else "production",
        receipt_number=_receipt_number() if succeeded else None,
    ))


def _record_refund(db: Session, event: dict) -> None:
    # RevenueCat reports refunds as CANCELLATION with cancel_reason CUSTOMER_SUPPORT.
    if event.get("type") != "CANCELLATION" or event.get("cancel_reason") != "CUSTOMER_SUPPORT":
        return
    txn = db.execute(select(PaymentTransaction).where(
        PaymentTransaction.provider == normalise_store(event.get("store")),
        PaymentTransaction.provider_transaction_id == event.get("transaction_id"),
    )).scalar_one_or_none()
    if txn is not None and txn.status == "succeeded":
        txn.status, txn.status_changed_at = "refunded", utcnow()


def process_webhook(db: Session, payload: dict) -> str:
    event = payload.get("event") if isinstance(payload, dict) else None
    if not isinstance(event, dict) or not event.get("id") or not event.get("type"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, {"code": "invalid_event", "message": "Malformed event."})

    row = db.execute(select(WebhookEvent).where(
        WebhookEvent.provider == PROVIDER, WebhookEvent.event_id == str(event["id"]),
    )).scalar_one_or_none()
    if row is not None and row.status in ("processed", "ignored"):
        return "duplicate"
    if row is None:
        row = WebhookEvent(provider=PROVIDER, event_id=str(event["id"])[:200], event_type=str(event["type"])[:64])
        db.add(row)
        try:
            db.commit()
        except IntegrityError:  # the same event is being processed concurrently
            db.rollback()
            return "duplicate"
    row.summary = {  # non-sensitive fields only — no receipts, no prices tied to identity
        "type": event.get("type"), "store": event.get("store"), "environment": event.get("environment"),
        "product_id": event.get("product_id"),
    }

    user_ids = _user_ids(db, event)
    if event["type"] == "TEST" or not user_ids:
        row.status, row.processed_at = "ignored", utcnow()
        db.commit()
        return "ignored"

    try:
        for uid in user_ids:
            _record_transaction(db, uid, event)
        _record_refund(db, event)
        db.commit()
        for uid in user_ids:
            sync_user(db, uid)
    except RevenueCatError as exc:
        db.rollback()
        row = db.get(WebhookEvent, row.id)
        row.status, row.error = "failed", str(exc)[:500]
        db.commit()
        logger.error("RevenueCat webhook %s failed: %s", event["id"], exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            {"code": "provider_unavailable", "message": "Try again later."}) from None

    row.status, row.processed_at, row.error = "processed", utcnow(), None
    db.commit()
    return "processed"


# ---------------------------------------------------------------- ledger

def list_transactions(db: Session, user_id: uuid.UUID) -> list[PaymentTransaction]:
    return list(db.execute(
        select(PaymentTransaction).where(PaymentTransaction.user_id == user_id)
        .order_by(PaymentTransaction.purchased_at.desc())
    ).scalars())


def get_transaction(db: Session, user_id: uuid.UUID, txn_id: uuid.UUID) -> PaymentTransaction:
    txn = db.get(PaymentTransaction, txn_id)
    if txn is None or txn.user_id != user_id:  # same 404 for "not yours" and "doesn't exist"
        raise HTTPException(status.HTTP_404_NOT_FOUND, {"code": "not_found", "message": "Payment not found."})
    return txn
