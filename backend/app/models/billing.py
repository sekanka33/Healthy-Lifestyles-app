import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPK, utcnow
from app.models.user import in_check

STORES = ("app_store", "play_store", "stripe", "promotional")


class SubscriptionEntitlement(UUIDPK, Timestamps, Base):
    """Server-side source of truth for Premium access. Only written after verifying with RevenueCat."""

    __tablename__ = "subscription_entitlements"
    __table_args__ = (
        UniqueConstraint("user_id", "entitlement"),
        in_check("status", ("active", "grace_period", "billing_issue", "cancelled", "expired", "refunded")),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    entitlement: Mapped[str] = mapped_column(String(32), default="premium")
    status: Mapped[str] = mapped_column(String(16))
    store: Mapped[str | None] = mapped_column(String(16))
    product_id: Mapped[str | None] = mapped_column(String(100))
    original_transaction_id: Mapped[str | None] = mapped_column(String(200))
    current_period_start: Mapped[datetime | None]
    expires_at: Mapped[datetime | None]
    will_renew: Mapped[bool] = mapped_column(Boolean, default=False)
    environment: Mapped[str] = mapped_column(String(16), default="production")  # or "sandbox"
    last_verified_at: Mapped[datetime | None]


class PaymentTransaction(UUIDPK, Timestamps, Base):
    """A verified charge. Amount/currency/reference are immutable once written; only status may move
    (e.g. succeeded -> refunded). Receipts are regenerated from this row on demand."""

    __tablename__ = "payment_transactions"
    __table_args__ = (
        UniqueConstraint("provider", "provider_transaction_id"),
        in_check("provider", STORES),
        in_check("status", ("succeeded", "pending", "failed", "refunded", "chargeback")),
        in_check("kind", ("initial_purchase", "renewal", "restore", "product_change")),
        Index("ix_payment_transactions_user", "user_id", "purchased_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(16))
    provider_transaction_id: Mapped[str] = mapped_column(String(200))
    original_transaction_id: Mapped[str | None] = mapped_column(String(200))
    product_id: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))  # as verified, never assumed
    currency: Mapped[str | None] = mapped_column(String(3))
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))  # only if provider supplies it
    purchased_at: Mapped[datetime]
    period_start: Mapped[datetime | None]
    period_end: Mapped[datetime | None]
    environment: Mapped[str] = mapped_column(String(16), default="production")
    receipt_number: Mapped[str | None] = mapped_column(String(40), unique=True)  # only for succeeded
    status_changed_at: Mapped[datetime | None]


class WebhookEvent(UUIDPK, Base):
    """Idempotency + audit log for inbound webhooks (payment and email providers)."""

    __tablename__ = "webhook_events"
    __table_args__ = (
        UniqueConstraint("provider", "event_id"),
        in_check("status", ("received", "processed", "ignored", "failed")),
    )

    provider: Mapped[str] = mapped_column(String(32))
    event_id: Mapped[str] = mapped_column(String(200))
    event_type: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(default=utcnow)
    processed_at: Mapped[datetime | None]
    status: Mapped[str] = mapped_column(String(16), default="received")
    error: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[dict | None] = mapped_column(JSON)  # redacted, non-sensitive fields only


class Job(UUIDPK, Base):
    """Durable background job (emails, reports, receipts). Processed by `python -m app.worker`."""

    __tablename__ = "jobs"
    __table_args__ = (
        in_check("status", ("queued", "running", "succeeded", "failed", "dead")),
        Index("ix_jobs_status_run_after", "status", "run_after"),
    )

    kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)  # ids only — never secrets or codes
    idempotency_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    run_after: Mapped[datetime] = mapped_column(default=utcnow)
    locked_at: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None]


class EmailMessage(UUIDPK, Base):
    """Delivery tracking. 'accepted' means the provider took it; only provider events set 'delivered'."""

    __tablename__ = "email_messages"
    __table_args__ = (
        in_check("status", ("queued", "sending", "accepted", "delivered", "bounced", "complained", "failed")),
        Index("ix_email_messages_user", "user_id"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    to_email: Mapped[str] = mapped_column(String(320))
    template: Mapped[str] = mapped_column(String(64))
    subject: Mapped[str] = mapped_column(String(255))
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    provider: Mapped[str | None] = mapped_column(String(32))
    provider_message_id: Mapped[str | None] = mapped_column(String(200), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    accepted_at: Mapped[datetime | None]
    delivered_at: Mapped[datetime | None]
