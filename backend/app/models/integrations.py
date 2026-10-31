import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPK, utcnow
from app.models.user import in_check


class OAuthConnection(UUIDPK, Timestamps, Base):
    """Google Calendar connection. Tokens are Fernet-encrypted at rest."""

    __tablename__ = "oauth_connections"
    __table_args__ = (
        UniqueConstraint("user_id", "provider"),
        in_check("provider", ("google",)),
        in_check("status", ("active", "revoked", "error")),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(16), default="google")
    account_email: Mapped[str | None] = mapped_column(String(320))
    scopes: Mapped[str] = mapped_column(Text)  # space separated, as granted
    refresh_token_enc: Mapped[str | None] = mapped_column(Text)
    access_token_enc: Mapped[str | None] = mapped_column(Text)
    access_token_expires_at: Mapped[datetime | None]
    selected_calendar_ids: Mapped[list] = mapped_column(JSON, default=lambda: ["primary"])
    status: Mapped[str] = mapped_column(String(16), default="active")
    last_error: Mapped[str | None] = mapped_column(String(255))


class OAuthState(UUIDPK, Base):
    """Pending OAuth authorisation: state (hashed) + PKCE verifier (encrypted), single use."""

    __tablename__ = "oauth_states"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    state_hash: Mapped[str] = mapped_column(String(64), unique=True)
    code_verifier_enc: Mapped[str] = mapped_column(Text)
    requested_scopes: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]
    consumed_at: Mapped[datetime | None]


class ActivityRecommendation(UUIDPK, Base):
    __tablename__ = "activity_recommendations"
    __table_args__ = (
        in_check("status", ("suggested", "accepted", "dismissed", "scheduled")),
        Index("ix_activity_recommendations_user_start", "user_id", "suggested_start"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))  # open set: engine is pluggable
    title: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(Text)
    slot_start: Mapped[datetime]
    slot_end: Mapped[datetime]
    suggested_start: Mapped[datetime]
    suggested_end: Mapped[datetime]
    weather_snapshot: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="suggested")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class CalendarEventRecord(UUIDPK, Base):
    """Events this app created in Google Calendar, only after explicit user approval."""

    __tablename__ = "calendar_event_records"
    __table_args__ = (UniqueConstraint("user_id", "google_event_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("activity_recommendations.id", ondelete="SET NULL")
    )
    calendar_id: Mapped[str] = mapped_column(String(255))
    google_event_id: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(200))
    start_at: Mapped[datetime]
    end_at: Mapped[datetime]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class WeatherCache(Base):
    __tablename__ = "weather_cache"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)  # e.g. "current:-26.20:28.05:metric"
    fetched_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    payload: Mapped[dict] = mapped_column(JSON)
