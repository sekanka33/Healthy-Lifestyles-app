import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Header, HTTPException, Response, status

from app.api.deps import DB, AnyUser
from app.core import rate_limit
from app.db.base import as_utc
from app.models.billing import PaymentTransaction
from app.schemas.billing import BillingStatusOut, EntitlementOut, TransactionOut
from app.services import billing
from app.services.entitlements import plan
from app.services.receipts import render_receipt
from app.services.revenuecat import RevenueCatError

router = APIRouter(prefix="/billing", tags=["billing"])


def _status(db, user) -> BillingStatusOut:
    ent = billing.get_entitlement(db, user.id)
    out = None
    if ent is not None:
        out = EntitlementOut(status=ent.status, product_id=ent.product_id, store=ent.store,
                             expires_at=as_utc(ent.expires_at) if ent.expires_at else None, will_renew=ent.will_renew,
                             environment=ent.environment,
                             last_verified_at=as_utc(ent.last_verified_at) if ent.last_verified_at else None)
    return BillingStatusOut(plan=plan(db, user), entitlement=out)


def _txn_out(t: PaymentTransaction) -> TransactionOut:
    return TransactionOut(
        id=t.id, provider=t.provider, product_id=t.product_id, kind=t.kind, status=t.status, amount=t.amount,
        currency=t.currency, purchased_at=as_utc(t.purchased_at),
        period_end=as_utc(t.period_end) if t.period_end else None, environment=t.environment,
        receipt_number=t.receipt_number, has_receipt=t.receipt_number is not None,
    )


@router.get("/status", response_model=BillingStatusOut)
def get_status(user: AnyUser, db: DB):
    return _status(db, user)


@router.post("/sync", response_model=BillingStatusOut)
def sync(user: AnyUser, db: DB):
    """Called by the app after a purchase or restore. The body is ignored on purpose: the server asks
    RevenueCat directly, so a modified app can't claim a purchase that didn't happen."""
    rate_limit.hit(db, f"billing-sync:user:{user.id}", limit=20, window_seconds=600)
    try:
        billing.sync_user(db, user.id)
    except RevenueCatError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            {"code": "provider_unavailable", "message": "Couldn't confirm your subscription. Try again shortly."}) from None
    return _status(db, user)


@router.get("/transactions", response_model=list[TransactionOut])
def transactions(user: AnyUser, db: DB):
    return [_txn_out(t) for t in billing.list_transactions(db, user.id)]


@router.get("/transactions/{txn_id}/receipt.pdf", response_class=Response,
            responses={200: {"content": {"application/pdf": {}}}})
def receipt(txn_id: uuid.UUID, user: AnyUser, db: DB):
    txn = billing.get_transaction(db, user.id, txn_id)
    if txn.receipt_number is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            {"code": "no_receipt", "message": "There is no receipt for this payment."})
    return Response(render_receipt(txn, user), media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="receipt-{txn.receipt_number}.pdf"',
        "Cache-Control": "private, no-store",
    })


@router.post("/webhooks/revenuecat", include_in_schema=False)
def revenuecat_webhook(
    db: DB,
    payload: Annotated[dict, Body()],
    authorization: Annotated[str | None, Header()] = None,
):
    billing.check_webhook_auth(authorization)
    return {"status": billing.process_webhook(db, payload)}
