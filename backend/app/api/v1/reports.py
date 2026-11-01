import base64
import hashlib
import hmac
import json
import time
from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, VerifiedUser
from app.core import rate_limit
from app.core.config import get_settings
from app.db.base import utcnow
from app.models.billing import EmailMessage, WebhookEvent
from app.models.user import EmailPreferences
from app.services import jobs, reports
from app.services.email_links import CATEGORIES, verify
from app.services.entitlements import is_premium
from app.services.hydration import local_today

router = APIRouter(tags=["reports & email"])

Kind = Literal["water", "fitness", "medication"]
Freq = Literal["off", "daily", "weekly", "monthly"]


def _range(user, period: str, from_: date | None, to: date | None) -> tuple[date, date]:
    if from_ or to:
        last = to or local_today(user)
        first = from_ or last - timedelta(days=6)
        if last < first or (last - first).days > 92:
            raise HTTPException(422, {"code": "invalid_range", "message": "Choose a range of up to 93 days."})
        return first, last
    today = local_today(user)
    if period == "this_week":
        return today - timedelta(days=today.isoweekday() - 1), today
    if period == "this_month":
        return today.replace(day=1), today
    return reports.previous_period(today, period)  # daily | weekly | monthly = the last complete one


Period = Literal["this_week", "this_month", "daily", "weekly", "monthly"]


def _check_plan(db, user, kind: str) -> None:
    if kind in reports.PREMIUM_KINDS and not is_premium(db, user):
        raise HTTPException(402, {"code": "premium_required", "message": "This report needs Healthy Lifestyles Premium."})


@router.get("/reports/{kind}.pdf", response_class=Response, responses={200: {"content": {"application/pdf": {}}}})
def report_pdf(kind: Kind, user: VerifiedUser, db: DB, period: Period = "this_week",
               from_: Annotated[date | None, Query(alias="from")] = None, to: date | None = None):
    _check_plan(db, user, kind)
    rate_limit.hit(db, f"report-pdf:user:{user.id}", limit=30, window_seconds=600)
    first, last = _range(user, period, from_, to)
    pdf = reports.render_pdf(reports.build(db, user, kind, first, last), user)
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{kind}-report-{first}-{last}.pdf"', "Cache-Control": "private, no-store"})


@router.post("/reports/{kind}/email", status_code=status.HTTP_202_ACCEPTED)
def email_report(kind: Kind, user: VerifiedUser, db: DB, period: Period = "this_week"):
    """Queues the report to the account's verified email (sent by the worker)."""
    _check_plan(db, user, kind)
    rate_limit.hit(db, f"report-email:user:{user.id}", limit=5, window_seconds=3600)
    first, last = _range(user, period, None, None)
    key = f"manual-report:{user.id}:{kind}:{first}:{last}:{int(time.time() // 300)}"  # one per 5 min
    jobs.enqueue(db, "email_report", {"user_id": str(user.id), "kind": kind, "first": first.isoformat(),
                                      "last": last.isoformat(), "scheduled": False, "key": key}, idempotency_key=key)
    return {"status": "queued", "to": user.email}


# ---------------------------------------------------------------- preferences & unsubscribe

class EmailPrefs(BaseModel):
    water_summary: Freq
    fitness_report: Freq
    medication_report: Freq
    medication_report_detail: Literal["summary_only", "detailed"]
    combined_weekly_report: bool
    subscription_lifecycle_emails: bool
    product_updates: bool


class EmailPrefsIn(BaseModel):
    water_summary: Freq | None = None
    fitness_report: Freq | None = None
    medication_report: Freq | None = None
    medication_report_detail: Literal["summary_only", "detailed"] | None = None
    combined_weekly_report: bool | None = None
    subscription_lifecycle_emails: bool | None = None
    product_updates: bool | None = None


def _prefs(db, user) -> EmailPreferences:
    p = db.get(EmailPreferences, user.id)
    if p is None:
        p = EmailPreferences(user_id=user.id)
        db.add(p)
        db.commit()
    return p


def _prefs_out(p: EmailPreferences) -> EmailPrefs:
    return EmailPrefs(**{k: getattr(p, k) for k in EmailPrefs.model_fields})


@router.get("/me/email-preferences", response_model=EmailPrefs)
def get_email_prefs(user: VerifiedUser, db: DB):
    return _prefs_out(_prefs(db, user))


@router.patch("/me/email-preferences", response_model=EmailPrefs)
def patch_email_prefs(data: EmailPrefsIn, user: VerifiedUser, db: DB):
    p = _prefs(db, user)
    for k, v in data.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(p, k, v)
    db.commit()
    return _prefs_out(p)


def _unsubscribe(db, u: str, c: str, t: str) -> bool:
    uid = verify(u, c, t)
    if uid is None:
        return False
    p = db.get(EmailPreferences, uid)
    if p is not None:
        field, off = CATEGORIES[c]
        setattr(p, field, off)
        db.commit()
    return True


@router.get("/email/unsubscribe", response_class=HTMLResponse, include_in_schema=False)
def unsubscribe_page(db: DB, u: str = "", c: str = "", t: str = ""):
    ok = _unsubscribe(db, u, c, t)
    msg = ("You're unsubscribed. You can turn these emails back on in the app under Profile → Email &amp; reports."
           if ok else "This unsubscribe link isn't valid. You can manage emails in the app under Profile → Email &amp; reports.")
    html = (f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{get_settings().app_name}</title><body style='font-family:system-ui;max-width:32rem;margin:3rem auto;"
            f"padding:0 1rem;color:#0B1E37'><h1>{get_settings().app_name}</h1><p>{msg}</p></body>")
    return HTMLResponse(html, status_code=200 if ok else 400)


@router.post("/email/unsubscribe", include_in_schema=False)
def unsubscribe_one_click(db: DB, u: str = "", c: str = "", t: str = ""):
    """RFC 8058 one-click: mail apps POST here directly."""
    if not _unsubscribe(db, u, c, t):
        raise HTTPException(400, {"code": "invalid_link", "message": "Invalid unsubscribe link."})
    return {"status": "unsubscribed"}


# ---------------------------------------------------------------- provider delivery webhook (Resend / Svix)

TOLERANCE_S = 5 * 60
STATUS = {"email.delivered": "delivered", "email.bounced": "bounced", "email.complained": "complained"}


def verify_svix(secret: str, msg_id: str, timestamp: str, body: bytes, signatures: str) -> bool:
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    if abs(time.time() - ts) > TOLERANCE_S:
        return False  # replay protection
    key = base64.b64decode(secret.removeprefix("whsec_"))
    expected = base64.b64encode(hmac.new(key, f"{msg_id}.{timestamp}.".encode() + body, hashlib.sha256).digest()).decode()
    return any(hmac.compare_digest(expected, part.split(",", 1)[1]) for part in signatures.split() if "," in part)


@router.post("/email/webhooks/resend", include_in_schema=False)
async def resend_webhook(request: Request, db: DB):
    secret = get_settings().resend_webhook_secret
    if not secret:
        raise HTTPException(503, {"code": "webhook_not_configured", "message": "Webhook secret is not configured."})
    body = await request.body()
    h = request.headers
    if not verify_svix(secret, h.get("svix-id", ""), h.get("svix-timestamp", ""), body, h.get("svix-signature", "")):
        raise HTTPException(401, {"code": "invalid_signature", "message": "Unauthorized."})
    event = json.loads(body or b"{}")
    event_id = h["svix-id"]
    try:
        db.add(WebhookEvent(provider="resend", event_id=event_id, event_type=str(event.get("type", ""))[:64]))
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"status": "duplicate"}
    row = db.execute(select(WebhookEvent).where(WebhookEvent.provider == "resend",
                                                WebhookEvent.event_id == event_id)).scalar_one()
    new_status = STATUS.get(event.get("type"))
    email_id = (event.get("data") or {}).get("email_id")
    msg = db.execute(select(EmailMessage).where(EmailMessage.provider_message_id == email_id)).scalar_one_or_none() if email_id else None
    if new_status and msg is not None:
        msg.status = new_status
        if new_status == "delivered":
            msg.delivered_at = utcnow()
        row.status = "processed"
    else:
        row.status = "ignored"
    row.processed_at = utcnow()
    db.commit()
    return {"status": row.status}
