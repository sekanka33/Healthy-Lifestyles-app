import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPK, utcnow
from app.models.user import in_check


class HydrationGoal(UUIDPK, Base):
    """Daily goal history. The goal in effect on a day is the latest row with effective_from <= day,
    so changing the goal never rewrites past reports."""

    __tablename__ = "hydration_goals"
    __table_args__ = (
        UniqueConstraint("user_id", "effective_from"),
        CheckConstraint("daily_goal_ml BETWEEN 250 AND 10000", name="goal_range"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    daily_goal_ml: Mapped[int] = mapped_column(Integer)
    effective_from: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class HydrationEntry(UUIDPK, Base):
    __tablename__ = "hydration_entries"
    __table_args__ = (
        # client_id is generated on the device: retries / double taps / offline replays are idempotent.
        UniqueConstraint("user_id", "client_id"),
        CheckConstraint("volume_ml BETWEEN 1 AND 5000", name="volume_range"),
        in_check("source", ("app", "reminder", "import")),
        Index("ix_hydration_entries_user_time", "user_id", "consumed_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    volume_ml: Mapped[int] = mapped_column(Integer)
    consumed_at: Mapped[datetime]
    source: Mapped[str] = mapped_column(String(16), default="app")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    # Undo is a soft delete so the deletion can sync to other devices; excluded from totals.
    deleted_at: Mapped[datetime | None]
