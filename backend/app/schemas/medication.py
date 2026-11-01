import re
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import validate_timezone

ScheduleType = Literal["daily", "specific_days", "every_n_days", "as_needed"]
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
MAX_TIMES = 12


def _times(v: list[str] | None) -> list[str] | None:
    if v is None:
        return v
    for t in v:
        if not HHMM.match(t):
            raise ValueError("Times must look like 08:00 (24-hour)")
    return sorted(set(v))


def _days(v: list[int] | None) -> list[int] | None:
    if v is None:
        return v
    if not v or any(d < 1 or d > 7 for d in v):
        raise ValueError("Days must be 1 (Monday) to 7 (Sunday)")
    return sorted(set(v))


def _tz(v: str | None) -> str | None:
    return validate_timezone(v) if v is not None else v


def _strip(v: str | None) -> str | None:
    return v.strip() if v is not None else v


class MedicationBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    # Exactly as given by the user's healthcare professional. Stored verbatim, never altered.
    dosage_instructions: str = Field(min_length=1, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)
    schedule_type: ScheduleType
    times: list[str] = Field(default_factory=list, max_length=MAX_TIMES)
    days_of_week: list[int] | None = None
    interval_days: int | None = Field(default=None, ge=2, le=90)
    timezone: str | None = None  # defaults to the user's zone
    start_date: date | None = None  # defaults to today (local)
    end_date: date | None = None
    reminders_enabled: bool = True

    _s = field_validator("name", "dosage_instructions", "notes")(_strip)
    _t = field_validator("times")(_times)
    _d = field_validator("days_of_week")(_days)
    _z = field_validator("timezone")(_tz)

    @model_validator(mode="after")
    def consistent(self):
        check_schedule(self.schedule_type, self.times, self.days_of_week, self.interval_days,
                       self.start_date, self.end_date)
        return self


def check_schedule(schedule_type, times, days_of_week, interval_days, start_date, end_date) -> None:
    if schedule_type != "as_needed" and not times:
        raise ValueError("Add at least one time")
    if schedule_type == "specific_days" and not days_of_week:
        raise ValueError("Choose at least one day")
    if schedule_type == "every_n_days" and not interval_days:
        raise ValueError("interval_days is required for every_n_days")
    if start_date and end_date and end_date < start_date:
        raise ValueError("end_date must be on or after start_date")


class MedicationCreate(MedicationBase):
    pass


class MedicationUpdate(BaseModel):
    """Partial update. The merged result is re-validated in the service."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    dosage_instructions: str | None = Field(default=None, min_length=1, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)
    schedule_type: ScheduleType | None = None
    times: list[str] | None = Field(default=None, max_length=MAX_TIMES)
    days_of_week: list[int] | None = None
    interval_days: int | None = Field(default=None, ge=2, le=90)
    timezone: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    reminders_enabled: bool | None = None

    _s = field_validator("name", "dosage_instructions", "notes")(_strip)
    _t = field_validator("times")(_times)
    _d = field_validator("days_of_week")(_days)
    _z = field_validator("timezone")(_tz)


class MedicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    dosage_instructions: str
    notes: str | None
    schedule_type: ScheduleType
    times: list[str]
    days_of_week: list[int] | None
    interval_days: int | None
    timezone: str
    start_date: date
    end_date: date | None
    reminders_enabled: bool
    discontinued_at: datetime | None
    active: bool
    created_at: datetime


DoseStatus = Literal["taken", "skipped", "missed"]


class DoseIn(BaseModel):
    scheduled_for: AwareDatetime  # the dose time from /medications/schedule (or "now" for as-needed)
    status: DoseStatus
    note: str | None = Field(default=None, max_length=500)


class DoseOut(BaseModel):
    medication_id: uuid.UUID
    scheduled_for: datetime
    status: DoseStatus
    recorded_at: datetime
    note: str | None


class ScheduledDose(BaseModel):
    medication_id: uuid.UUID
    medication_name: str
    dosage_instructions: str
    scheduled_for: datetime
    # Recorded outcome, or: "upcoming" (in the future) / "unrecorded" (past, nothing logged).
    # Unrecorded doses are never assumed taken.
    status: Literal["taken", "skipped", "missed", "upcoming", "unrecorded"]
    recorded_at: datetime | None
    note: str | None


class AdherenceRow(BaseModel):
    medication_id: uuid.UUID
    medication_name: str
    scheduled: int
    taken: int
    skipped: int
    missed: int
    unrecorded: int
    as_needed_taken: int
    adherence: float | None  # taken / (scheduled doses that are due); None when nothing was due


class AdherenceOut(BaseModel):
    from_date: date
    to_date: date
    timezone: str
    medications: list[AdherenceRow]
