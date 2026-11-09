"""Back-office accounts. Deliberately separate from app `users`: an app account can never become an
admin by changing a flag, and an admin credential is never valid in the mobile API."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BigIntPK, Base, Timestamps, UUIDPK, utcnow
from app.models.user import in_check

ADMIN_ROLES = ("owner", "admin", "support", "finance", "technical")


class AdminUser(UUIDPK, Timestamps, Base):
    __tablename__ = "admin_users"
    __table_args__ = (in_check("role", ADMIN_ROLES),)

    email: Mapped[str] = mapped_column(String(320), unique=True)  # stored lower-cased
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    password_changed_at: Mapped[datetime | None]
    last_login_at: Mapped[datetime | None]
    # TOTP (RFC 6238). Secret is Fernet-encrypted; set while enrolling, active once mfa_enabled_at is set.
    mfa_secret_enc: Mapped[str | None] = mapped_column(String(255))
    mfa_enabled_at: Mapped[datetime | None]
    mfa_last_step: Mapped[int | None] = mapped_column(Integer)  # last accepted time step: blocks code replay


class AdminSession(UUIDPK, Base):
    """Server-side session: revocable at once, idle and absolute timeouts. Only a SHA-256 of the token is kept."""

    __tablename__ = "admin_sessions"
    __table_args__ = (Index("ix_admin_sessions_admin", "admin_id"),)

    admin_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("admin_users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    mfa_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))


class AuditLog(Base):
    """Append-only record of administrative actions. Never store secrets, codes or health data in `details`."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_created", "created_at"),
        Index("ix_audit_logs_action_created", "action", "created_at"),
        Index("ix_audit_logs_admin_created", "admin_id", "created_at"),
        Index("ix_audit_logs_resource", "resource_type", "resource_id"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    admin_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("admin_users.id", ondelete="SET NULL"))
    actor_email: Mapped[str | None] = mapped_column(String(320))  # snapshot: survives admin deletion
    action: Mapped[str] = mapped_column(String(64))  # e.g. "admin.login", "user.suspended"
    resource_type: Mapped[str | None] = mapped_column(String(64))
    resource_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
