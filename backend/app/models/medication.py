import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPK, utcnow
from app.models.user import in_check


class Medication(UUIDPK, Timestamps, Base):
    """A medication schedule exactly as the user entered it (from their healthcare professional).
    The app never alters dosage or instructions."""

    __tablename__ = "medications"
    __table_args__ = (
        in_check("schedule_type", ("daily", "specific_days", "every_n_days", "as_needed")),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="date_order"),
        Index("ix_medications_user", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    dosage_instructions: Mapped[str] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    schedule_type: Mapped[str] = mapped_column(String(16))
    times: Mapped[list] = mapped_column(JSON, default=list)  # local wall-clock times ["08:00","20:00"]
    days_of_week: Mapped[list | None] = mapped_column(JSON)  # ISO weekdays [1..7] for specific_days
    interval_days: Mapped[int | None] = mapped_column(Integer)
    timezone: Mapped[str] = mapped_column(String(64))  # zone the wall-clock times are in
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    discontinued_at: Mapped[datetime | None]


class MedicationDose(UUIDPK, Base):
    """A *recorded* dose outcome. A scheduled dose with no row is 'unrecorded' — never assumed taken."""

    __tablename__ = "medication_doses"
    __table_args__ = (
        UniqueConstraint("medication_id", "scheduled_for"),
        in_check("status", ("taken", "skipped", "missed")),
        Index("ix_medication_doses_user_time", "user_id", "scheduled_for"),
    )

    medication_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("medications.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    scheduled_for: Mapped[datetime]  # UTC instant of the scheduled local time
    status: Mapped[str] = mapped_column(String(16))
    recorded_at: Mapped[datetime] = mapped_column(default=utcnow)
    note: Mapped[str | None] = mapped_column(Text)
