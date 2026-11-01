"""Email with delivery tracking.

Every send creates an `EmailMessage` row, idempotent on `idempotency_key`, so a retried job never
emails twice. Status: queued → sending → accepted (provider took it) → delivered / bounced /
complained (only from the provider's signed webhook). Bodies are never persisted: security emails
contain one-time codes and reports contain health data.

- `queue_email` — from a request (sign-in codes): sends right after the response, in-process.
- `send_now` — from the background worker (reports, receipts, exports): sends synchronously and
  raises on failure so the job is retried with backoff.
"""

import base64
import logging
import smtplib
import uuid
from dataclasses import dataclass, field
from email.message import EmailMessage as MimeMessage
from email.utils import make_msgid

import httpx
from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import utcnow
from app.models.billing import EmailMessage

logger = logging.getLogger("app.email")


@dataclass(frozen=True)
class Attachment:
    filename: str
    content_type: str  # e.g. "application/pdf"
    data: bytes


@dataclass(frozen=True)
class OutgoingEmail:
    to: str
    subject: str
    text: str
    attachments: tuple[Attachment, ...] = ()
    headers: dict = field(default_factory=dict)  # e.g. List-Unsubscribe


# In the test environment the "disabled" provider records messages here instead of sending.
TEST_OUTBOX: list[OutgoingEmail] = []


class EmailProvider:
    name = "base"

    def send(self, msg: OutgoingEmail) -> str | None:  # returns provider message id
        raise NotImplementedError


class DisabledProvider(EmailProvider):
    name = "disabled"

    def send(self, msg: OutgoingEmail) -> str | None:
        settings = get_settings()
        if settings.environment == "test":
            TEST_OUTBOX.append(msg)
        elif settings.environment == "development":
            # Dev convenience only: lets you sign up without a mail server. Never in production.
            names = ", ".join(a.filename for a in msg.attachments) or "none"
            logger.warning("EMAIL_PROVIDER=disabled — email not sent.\nTo: %s\nSubject: %s\nAttachments: %s\n\n%s",
                           msg.to, msg.subject, names, msg.text)
        return None


class SmtpProvider(EmailProvider):
    name = "smtp"

    def send(self, msg: OutgoingEmail) -> str | None:
        s = get_settings()
        mime = MimeMessage()
        mime["From"], mime["To"], mime["Subject"] = s.email_from, msg.to, msg.subject
        mime["Message-ID"] = make_msgid(domain="healthylifestyles")
        for k, v in msg.headers.items():
            mime[k] = v
        mime.set_content(msg.text)
        for a in msg.attachments:
            maintype, subtype = a.content_type.split("/", 1)
            mime.add_attachment(a.data, maintype=maintype, subtype=subtype, filename=a.filename)
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            if s.smtp_starttls:
                smtp.starttls()
            if s.smtp_username:
                smtp.login(s.smtp_username, s.smtp_password or "")
            smtp.send_message(mime)
        return mime["Message-ID"]


class ResendProvider(EmailProvider):
    name = "resend"

    def send(self, msg: OutgoingEmail) -> str | None:
        s = get_settings()
        body: dict = {"from": s.email_from, "to": [msg.to], "subject": msg.subject, "text": msg.text}
        if msg.headers:
            body["headers"] = msg.headers
        if msg.attachments:
            body["attachments"] = [{"filename": a.filename, "content": base64.b64encode(a.data).decode()}
                                   for a in msg.attachments]
        res = httpx.post("https://api.resend.com/emails", headers={"Authorization": f"Bearer {s.resend_api_key}"},
                         json=body, timeout=30)
        res.raise_for_status()
        return res.json().get("id")


def get_provider() -> EmailProvider:
    return {"smtp": SmtpProvider, "resend": ResendProvider}.get(get_settings().email_provider, DisabledProvider)()


def _row(db: Session, *, to: str, template: str, subject: str, idempotency_key: str,
         user_id: uuid.UUID | None) -> tuple[EmailMessage, bool]:
    existing = db.execute(select(EmailMessage).where(EmailMessage.idempotency_key == idempotency_key)).scalar_one_or_none()
    if existing is not None:
        return existing, False
    row = EmailMessage(user_id=user_id, to_email=to, template=template, subject=subject, idempotency_key=idempotency_key)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return db.execute(select(EmailMessage).where(EmailMessage.idempotency_key == idempotency_key)).scalar_one(), False
    return row, True


def _attempt(db: Session, row: EmailMessage, msg: OutgoingEmail) -> None:
    provider = get_provider()
    row.status, row.provider, row.attempts = "sending", provider.name, row.attempts + 1
    db.commit()
    try:
        row.provider_message_id = provider.send(msg)
        row.status, row.accepted_at, row.last_error = "accepted", utcnow(), None
        db.commit()
    except Exception as exc:  # provider/network failure: record it, then let the caller decide
        logger.error("Email %s failed via %s: %s", row.id, provider.name, type(exc).__name__)
        row.status, row.last_error = "failed", type(exc).__name__[:500]
        db.commit()
        raise


def send_now(db: Session, *, to: str, template: str, subject: str, text: str, idempotency_key: str,
             user_id: uuid.UUID | None = None, attachments: tuple[Attachment, ...] = (),
             headers: dict | None = None) -> EmailMessage:
    """Synchronous send for the worker. Already-accepted messages are not sent again."""
    row, _ = _row(db, to=to, template=template, subject=subject, idempotency_key=idempotency_key, user_id=user_id)
    if row.status in ("accepted", "delivered", "bounced", "complained"):
        return row
    _attempt(db, row, OutgoingEmail(to=to, subject=subject, text=text, attachments=attachments, headers=headers or {}))
    return row


def _deliver(message_id: uuid.UUID, msg: OutgoingEmail) -> None:
    from app.db.session import SessionLocal  # late import: tests swap the session factory

    with SessionLocal() as db:
        row = db.get(EmailMessage, message_id)
        if row is None or row.status not in ("queued", "failed"):
            return
        try:
            _attempt(db, row, msg)
        except Exception:
            pass  # recorded on the row; request-time emails (codes) are re-requested by the user


def queue_email(
    db: Session,
    background: BackgroundTasks,
    *,
    to: str,
    template: str,
    subject: str,
    text: str,
    idempotency_key: str,
    user_id: uuid.UUID | None = None,
) -> EmailMessage:
    row, created = _row(db, to=to, template=template, subject=subject, idempotency_key=idempotency_key, user_id=user_id)
    if created:
        background.add_task(_deliver, row.id, OutgoingEmail(to=to, subject=subject, text=text))
    return row
