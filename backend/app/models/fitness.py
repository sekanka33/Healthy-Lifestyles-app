import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BigIntPK, Base, Timestamps, UUIDPK, utcnow
from app.models.user import in_check

ACTIVITY_TYPES = ("walking", "running", "jogging")


class Workout(UUIDPK, Timestamps, Base):
    __tablename__ = "workouts"
    __table_args__ = (
        UniqueConstraint("user_id", "client_id"),
        # Prevents importing the same Health Connect / HealthKit record twice.
        UniqueConstraint("user_id", "source", "external_id"),
        in_check("activity_type", ACTIVITY_TYPES),
        in_check("source", ("gps", "manual", "health_connect", "healthkit")),
        in_check("status", ("in_progress", "completed", "discarded")),
        CheckConstraint("distance_m >= 0", name="distance_nonneg"),
        Index("ix_workouts_user_start", "user_id", "started_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    activity_type: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(16))
    external_id: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default="in_progress")
    started_at: Mapped[datetime]
    ended_at: Mapped[datetime | None]
    active_duration_s: Mapped[int] = mapped_column(Integer, default=0)  # excludes paused time
    distance_m: Mapped[float] = mapped_column(default=0.0)
    calories_kcal_estimate: Mapped[float | None]  # always presented as an estimate
    steps: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)


class WorkoutPoint(Base):
    __tablename__ = "workout_points"
    __table_args__ = (UniqueConstraint("workout_id", "seq"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    workout_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("workouts.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    segment: Mapped[int] = mapped_column(Integer, default=0)  # increments on resume after pause
    recorded_at: Mapped[datetime]
    lat: Mapped[float]
    lon: Mapped[float]
    altitude_m: Mapped[float | None]
    accuracy_m: Mapped[float | None]
    speed_mps: Mapped[float | None]
    accepted: Mapped[bool] = mapped_column(Boolean, default=True)  # False = filtered (jump / low accuracy)


class FitnessGoal(UUIDPK, Timestamps, Base):
    __tablename__ = "fitness_goals"
    __table_args__ = (
        in_check("metric", ("distance_km", "workout_count", "active_minutes")),
        in_check("period", ("weekly", "monthly")),
        CheckConstraint("target_value > 0", name="target_positive"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    metric: Mapped[str] = mapped_column(String(32))
    period: Mapped[str] = mapped_column(String(16))
    target_value: Mapped[float]
    activity_type: Mapped[str | None] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class HealthConnection(UUIDPK, Base):
    __tablename__ = "health_connections"
    __table_args__ = (
        UniqueConstraint("user_id", "provider"),
        in_check("provider", ("health_connect", "healthkit")),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(32))
    granted_data_types: Mapped[list] = mapped_column(JSON, default=list)
    connected_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_synced_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]
