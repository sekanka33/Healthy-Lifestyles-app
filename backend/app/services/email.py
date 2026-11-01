"""Transactional email with delivery tracking.

Each send creates an `EmailMessage` row (idempotent on `idempotency_key`) and is handed to the
configured provider after the response is sent (FastAPI background task). The rendered body is
never persisted, because security emails contain one-time codes.

Phase 10 adds provider delivery webhooks (accepted -> delivered/bounced) and report emails.
"""

import logging
import smtplib
import uuid
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from email.utils import make_msgid

import httpx
from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import utcnow
from app.models.billing import EmailMessage

logger = logging.getLogger("app.email")


@dataclass(frozen=True)
class OutgoingEmail:
    to: str
    subject: str
    text: str


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
            logger.warning("EMAIL_PROVIDER=disabled — email not sent.\nTo: %s\nSubject: %s\n\n%s",
                           msg.to, msg.subject, msg.text)
        return None


class SmtpProvider(EmailProvider):
    name = "smtp"

    def send(self, msg: OutgoingEmail) -> str | None:
        s = get_settings()
        mime = MimeMessage()
        mime["From"], mime["To"], mime["Subject"] = s.email_from, msg.to, msg.subject
        mime["Message-ID"] = make_msgid(domain="healthylifestyles")
        mime.set_content(msg.text)
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
        res = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {s.resend_api_key}"},
            json={"from": s.email_from, "to": [msg.to], "subject": msg.subject, "text": msg.text},
            timeout=15,
        )
        res.raise_for_status()
        return res.json().get("id")


def get_provider() -> EmailProvider:
    return {"smtp": SmtpProvider, "resend": ResendProvider}.get(get_settings().email_provider, DisabledProvider)()


def _deliver(message_id: uuid.UUID, msg: OutgoingEmail) -> None:
    from app.db.session import SessionLocal  # late import: tests swap the session factory

    provider = get_provider()
    with SessionLocal() as db:
        row = db.get(EmailMessage, message_id)
        if row is None or row.status not in ("queued", "failed"):
            return
        row.status, row.provider, row.attempts = "sending", provider.name, row.attempts + 1
        db.commit()
        try:
            row.provider_message_id = provider.send(msg)
            row.status, row.accepted_at = "accepted", utcnow()
        except Exception as exc:  # provider/network failure: record it, never crash the request
            logger.error("Email %s failed via %s: %s", message_id, provider.name, type(exc).__name__)
            row.status, row.last_error = "failed", f"{type(exc).__name__}"[:500]
        db.commit()


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
    existing = db.execute(
        select(EmailMessage).where(EmailMessage.idempotency_key == idempotency_key)
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    row = EmailMessage(user_id=user_id, to_email=to, template=template, subject=subject,
                       idempotency_key=idempotency_key)
    db.add(row)
    db.commit()
    background.add_task(_deliver, row.id, OutgoingEmail(to=to, subject=subject, text=text))
    return row
