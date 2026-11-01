"""Background job handlers (reports, receipts, data exports) and the report scheduler.

The scheduler runs inside the worker every minute. At or after 07:00 in each user's own time zone it
enqueues the reports they opted into for the period that just ended. Idempotency keys
(`report:{user}:{kind}:{first}:{last}`) make re-runs, restarts and multiple workers harmless.
"""

import uuid
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import utcnow
from app.models.billing import PaymentTransaction, WebhookEvent
from app.models.integrations import OAuthState
from app.models.user import EmailPreferences, OneTimeCode, RateLimitBucket, RefreshToken, User
from app.services import email as email_svc
from app.services import jobs, privacy, reports
from app.services.email_links import list_unsubscribe_headers, unsubscribe_url
from app.services.entitlements import is_premium
from app.services.receipts import render_receipt

SEND_HOUR = time(7, 0)
FIELD = {"water": "water_summary", "fitness": "fitness_report", "medication": "medication_report"}


def _user(db: Session, payload: dict) -> User:
    user = db.get(User, uuid.UUID(payload["user_id"]))
    if user is None or not user.is_active:
        raise jobs.PermanentJobError("user no longer exists")
    return user


def _prefs(db: Session, user: User) -> EmailPreferences:
    p = db.get(EmailPreferences, user.id)
    if p is None:
        p = EmailPreferences(user_id=user.id)
        db.add(p)
        db.commit()
    return p


def send_report(db: Session, user: User, kind: str, first, last, *, scheduled: bool, key: str) -> bool:
    """Builds and emails one report. Returns False when there was nothing to send."""
    if kind in reports.PREMIUM_KINDS and not is_premium(db, user):
        return False
    prefs = _prefs(db, user)
    report = reports.build(db, user, kind, first, last)
    if scheduled and report.empty:
        return False  # don't email "nothing happened" on a schedule
    detailed = kind != "medication" or prefs.medication_report_detail == "detailed"
    attachments = ()
    if detailed:
        pdf = reports.render_pdf(report, user)
        attachments = (email_svc.Attachment(f"{kind}-report-{first}.pdf", "application/pdf", pdf),)
    unsub = unsubscribe_url(user.id, kind) if scheduled else None
    email_svc.send_now(
        db, to=user.email, user_id=user.id, template=f"report_{kind}",
        # Subject lines show on lock screens: keep them free of health details.
        subject=f"Your {get_settings().app_name} {kind} report — {reports.label(first, last)}",
        text=reports.email_text(report, user, detailed=detailed, unsubscribe_url=unsub),
        idempotency_key=key, attachments=attachments,
        headers=list_unsubscribe_headers(user.id, kind) if scheduled else None,
    )
    return True


@jobs.handler("email_report")
def _job_report(db: Session, payload: dict) -> None:
    user = _user(db, payload)
    kind = payload["kind"]
    first, last = datetime.fromisoformat(payload["first"]).date(), datetime.fromisoformat(payload["last"]).date()
    if payload.get("scheduled"):
        prefs = _prefs(db, user)
        if getattr(prefs, FIELD[kind]) == "off":
            return  # turned off after it was queued
    send_report(db, user, kind, first, last, scheduled=bool(payload.get("scheduled")),
                key=f"email:{payload['key']}")


@jobs.handler("email_receipt")
def _job_receipt(db: Session, payload: dict) -> None:
    txn = db.get(PaymentTransaction, uuid.UUID(payload["transaction_id"]))
    if txn is None or txn.receipt_number is None:
        raise jobs.PermanentJobError("no receipt for this payment")
    user = db.get(User, txn.user_id)
    if user is None:
        raise jobs.PermanentJobError("user no longer exists")
    email_svc.send_now(
        db, to=user.email, user_id=user.id, template="payment_receipt",
        subject=f"Your {get_settings().app_name} receipt {txn.receipt_number}",
        text=(f"Hi {user.first_name},\n\nThanks for your payment. Your receipt {txn.receipt_number} is attached.\n"
              "The app store that processed the payment also sends its own invoice.\n\n— " + get_settings().app_name),
        idempotency_key=f"receipt:{txn.id}",
        attachments=(email_svc.Attachment(f"receipt-{txn.receipt_number}.pdf", "application/pdf", render_receipt(txn, user)),),
    )


@jobs.handler("email_export")
def _job_export(db: Session, payload: dict) -> None:
    user = _user(db, payload)
    email_svc.send_now(
        db, to=user.email, user_id=user.id, template="data_export",
        subject=f"Your {get_settings().app_name} data export",
        text=(f"Hi {user.first_name},\n\nAttached is a copy of the data we hold for your account (JSON).\n"
              "If you didn't ask for this, change your password and contact us.\n\n— " + get_settings().app_name),
        idempotency_key=f"export:{payload['key']}",
        attachments=(email_svc.Attachment("healthy-lifestyles-export.json", "application/json", privacy.export_bytes(db, user)),),
    )


# ---------------------------------------------------------------- scheduler

def schedule_due_reports(db: Session, now: datetime | None = None) -> int:
    """Enqueue every report that is due. Safe to call as often as you like."""
    now = now or utcnow()
    count = 0
    q = select(User, EmailPreferences).join(EmailPreferences, EmailPreferences.user_id == User.id).where(
        User.is_active.is_(True), User.email_verified_at.is_not(None))
    for user, prefs in db.execute(q).all():
        local = now.astimezone(ZoneInfo(user.timezone or "UTC"))
        if local.time() < SEND_HOUR:
            continue
        today = local.date()
        for kind, field in FIELD.items():
            freq = getattr(prefs, field)
            if freq == "off" or (freq == "weekly" and today.isoweekday() != 1) or (freq == "monthly" and today.day != 1):
                continue
            first, last = reports.previous_period(today, freq)
            key = f"report:{user.id}:{kind}:{first}:{last}"
            jobs.enqueue(db, "email_report", {"user_id": str(user.id), "kind": kind, "first": first.isoformat(),
                                              "last": last.isoformat(), "scheduled": True, "key": key},
                         idempotency_key=key)
            count += 1
    return count


def maintenance(db: Session) -> None:
    """Data minimisation: drop short-lived security records and old logs."""
    now = utcnow()
    db.execute(delete(OneTimeCode).where(OneTimeCode.expires_at < now - timedelta(days=1)))
    db.execute(delete(OAuthState).where(OAuthState.expires_at < now - timedelta(days=1)))
    db.execute(delete(RefreshToken).where(RefreshToken.expires_at < now - timedelta(days=7)))
    db.execute(delete(RateLimitBucket).where(RateLimitBucket.window_start < now - timedelta(days=1)))
    db.execute(delete(WebhookEvent).where(WebhookEvent.received_at < now - timedelta(days=90)))
    db.commit()
