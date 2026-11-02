import uuid
from datetime import datetime, time

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Time, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPK, utcnow


def in_check(column: str, values: tuple[str, ...], name: str | None = None) -> CheckConstraint:
    quoted = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{column} IN ({quoted})", name=name or f"{column}_valid")


class User(UUIDPK, Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (in_check("units", ("metric", "imperial")),)

    email: Mapped[str] = mapped_column(String(320), unique=True)  # stored lower-cased
    password_hash: Mapped[str] = mapped_column(String(255))
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    email_verified_at: Mapped[datetime | None]
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")  # IANA name
    locale: Mapped[str] = mapped_column(String(16), default="en")
    units: Mapped[str] = mapped_column(String(16), default="metric")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    password_changed_at: Mapped[datetime | None]

    preferences: Mapped["UserPreferences"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )


class UserPreferences(Timestamps, Base):
    """Scheduling & recommendation preferences (one row per user)."""

    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    working_hours_start: Mapped[time | None] = mapped_column(Time)
    working_hours_end: Mapped[time | None] = mapped_column(Time)
    sleep_start: Mapped[time] = mapped_column(Time, default=time(22, 0))
    sleep_end: Mapped[time] = mapped_column(Time, default=time(6, 30))
    min_free_slot_minutes: Mapped[int] = mapped_column(Integer, default=15)
    preferred_activities: Mapped[list] = mapped_column(JSON, default=list)  # e.g. ["walking","running"]
    preferred_activity_times: Mapped[list] = mapped_column(JSON, default=list)  # e.g. ["morning","evening"]
    use_medication_in_recommendations: Mapped[bool] = mapped_column(Boolean, default=False)
    body_weight_kg: Mapped[float | None]  # optional; only used for calorie *estimates*
    weather_location_name: Mapped[str | None] = mapped_column(String(120))
    weather_lat: Mapped[float | None]  # rounded to 2 dp (~1 km) for privacy
    weather_lon: Mapped[float | None]

    user: Mapped[User] = relationship(back_populates="preferences")


class NotificationPreferences(Timestamps, Base):
    __tablename__ = "notification_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    hydration_reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    hydration_reminder_interval_minutes: Mapped[int] = mapped_column(Integer, default=90)
    quiet_hours_start: Mapped[time | None] = mapped_column(Time, default=time(22, 0))
    quiet_hours_end: Mapped[time | None] = mapped_column(Time, default=time(7, 0))
    medication_reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    workout_reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


REPORT_FREQ = ("off", "daily", "weekly", "monthly")


class EmailPreferences(Timestamps, Base):
    """Optional email categories. Security & payment emails are transactional and not gated here."""

    __tablename__ = "email_preferences"
    __table_args__ = (
        in_check("water_summary", REPORT_FREQ),
        in_check("fitness_report", REPORT_FREQ),
        in_check("medication_report", REPORT_FREQ),
        in_check("medication_report_detail", ("summary_only", "detailed")),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    water_summary: Mapped[str] = mapped_column(String(16), default="off")
    medication_report: Mapped[str] = mapped_column(String(16), default="off")
    # Privacy default: emails only contain a summary; details require signing in.
    medication_report_detail: Mapped[str] = mapped_column(String(16), default="summary_only")
    fitness_report: Mapped[str] = mapped_column(String(16), default="off")
    combined_weekly_report: Mapped[bool] = mapped_column(Boolean, default=False)
    subscription_lifecycle_emails: Mapped[bool] = mapped_column(Boolean, default=True)
    product_updates: Mapped[bool] = mapped_column(Boolean, default=False)  # marketing — opt-in only


class RefreshToken(UUIDPK, Base):
    """Rotating refresh tokens. Only a SHA-256 hash is stored."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_user", "user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid)  # reuse of a rotated token revokes the family
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    user_agent: Mapped[str | None] = mapped_column(String(255))


class OneTimeCode(UUIDPK, Base):
    """Email verification codes and password-reset tokens (hashed, single-use, expiring)."""

    __tablename__ = "one_time_codes"
    __table_args__ = (
        in_check("purpose", ("email_verification", "password_reset")),
        Index("ix_one_time_codes_user_purpose", "user_id", "purpose"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(String(32))
    code_hash: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]
    consumed_at: Mapped[datetime | None]
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class RateLimitBucket(Base):
    """Fixed-window counters shared by all API workers (works without Redis)."""

    __tablename__ = "rate_limit_buckets"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    window_start: Mapped[datetime]
    count: Mapped[int] = mapped_column(Integer, default=0)
