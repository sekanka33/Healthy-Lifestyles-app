"""Medication schedules and dose records (Premium).

The app records what the user tells it. It never changes dosage or instructions, never infers that
a dose was taken, and reports unrecorded doses as "unrecorded" — not as taken or missed.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import as_utc, utcnow
from app.models.medication import Medication, MedicationDose
from app.models.user import User
from app.schemas.medication import (
    AdherenceRow,
    MedicationCreate,
    MedicationOut,
    MedicationUpdate,
    ScheduledDose,
    check_schedule,
)
from app.services.hydration import local_today
from app.services.medication_schedule import Schedule, is_occurrence, occurrences

MAX_MEDICATIONS = 50
MAX_RANGE_DAYS = 93
AS_NEEDED_SKEW = timedelta(minutes=5)
MAX_BACKFILL = timedelta(days=30)


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, {"code": "not_found", "message": "Medication not found."})


def _unprocessable(code: str, message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, {"code": code, "message": message})


def schedule_of(m: Medication) -> Schedule:
    return Schedule(
        schedule_type=m.schedule_type, times=list(m.times or []), timezone=m.timezone, start_date=m.start_date,
        end_date=m.end_date, days_of_week=m.days_of_week, interval_days=m.interval_days,
        discontinued_at=as_utc(m.discontinued_at) if m.discontinued_at else None,
    )


def to_out(m: Medication) -> MedicationOut:
    return MedicationOut(
        id=m.id, name=m.name, dosage_instructions=m.dosage_instructions, notes=m.notes,
        schedule_type=m.schedule_type, times=list(m.times or []), days_of_week=m.days_of_week,
        interval_days=m.interval_days, timezone=m.timezone, start_date=m.start_date, end_date=m.end_date,
        reminders_enabled=m.reminders_enabled,
        discontinued_at=as_utc(m.discontinued_at) if m.discontinued_at else None,
        active=m.discontinued_at is None, created_at=as_utc(m.created_at),
    )


def get_owned(db: Session, user: User, med_id: uuid.UUID) -> Medication:
    m = db.get(Medication, med_id)
    if m is None or m.user_id != user.id:  # same 404 whether missing or someone else's
        raise _not_found()
    return m


def list_medications(db: Session, user: User, include_discontinued: bool = True) -> list[Medication]:
    q = select(Medication).where(Medication.user_id == user.id)
    if not include_discontinued:
        q = q.where(Medication.discontinued_at.is_(None))
    return list(db.execute(q.order_by(Medication.discontinued_at.is_not(None), Medication.name)).scalars())


def create(db: Session, user: User, data: MedicationCreate) -> Medication:
    count = len(db.execute(select(Medication.id).where(Medication.user_id == user.id)).all())
    if count >= MAX_MEDICATIONS:
        raise _unprocessable("limit_reached", f"You can track up to {MAX_MEDICATIONS} medications.")
    m = Medication(
        user_id=user.id, name=data.name, dosage_instructions=data.dosage_instructions, notes=data.notes or None,
        schedule_type=data.schedule_type, times=[] if data.schedule_type == "as_needed" else data.times,
        days_of_week=data.days_of_week if data.schedule_type == "specific_days" else None,
        interval_days=data.interval_days if data.schedule_type == "every_n_days" else None,
        timezone=data.timezone or user.timezone, start_date=data.start_date or local_today(user),
        end_date=data.end_date, reminders_enabled=data.reminders_enabled,
    )
    db.add(m)
    db.commit()
    return m


def update(db: Session, user: User, m: Medication, data: MedicationUpdate) -> Medication:
    changes = data.model_dump(exclude_unset=True)
    for required in ("name", "dosage_instructions", "schedule_type", "times", "timezone", "start_date"):
        if required in changes and changes[required] is None:
            changes.pop(required)
    merged = {
        "schedule_type": changes.get("schedule_type", m.schedule_type),
        "times": changes.get("times", m.times),
        "days_of_week": changes.get("days_of_week", m.days_of_week),
        "interval_days": changes.get("interval_days", m.interval_days),
        "start_date": changes.get("start_date", m.start_date),
        "end_date": changes.get("end_date", m.end_date),
    }
    try:
        check_schedule(**merged)
    except ValueError as e:
        raise _unprocessable("invalid_schedule", str(e)) from None
    for field, value in changes.items():
        setattr(m, field, value)
    # Keep only the fields that apply to the chosen schedule type.
    if m.schedule_type == "as_needed":
        m.times = []
    if m.schedule_type != "specific_days":
        m.days_of_week = None
    if m.schedule_type != "every_n_days":
        m.interval_days = None
    db.commit()
    return m


def discontinue(db: Session, m: Medication) -> Medication:
    """Stops future doses and reminders; history is kept."""
    if m.discontinued_at is None:
        m.discontinued_at = utcnow()
        db.commit()
    return m


def resume(db: Session, user: User, m: Medication) -> Medication:
    if m.discontinued_at is not None:
        m.discontinued_at = None
        if m.end_date is not None and m.end_date < local_today(user):
            m.end_date = None
        db.commit()
    return m


def delete_medication(db: Session, m: Medication) -> None:
    """Permanently removes the medication and its dose history."""
    db.delete(m)
    db.commit()


# ---------------------------------------------------------------- doses

def record_dose(db: Session, user: User, m: Medication, scheduled_for: datetime, status_: str,
                note: str | None) -> tuple[MedicationDose, bool]:
    """Upsert the outcome for one dose (corrections allowed). Returns (dose, created)."""
    at = scheduled_for.astimezone(timezone.utc).replace(microsecond=0)
    now = utcnow()
    if m.schedule_type == "as_needed":
        if status_ != "taken":
            raise _unprocessable("invalid_status", "As-needed doses can only be recorded as taken.")
        if at > now + AS_NEEDED_SKEW:
            raise _unprocessable("future_dose", "You can't record a dose in the future.")
    else:
        if not is_occurrence(schedule_of(m), at):
            raise _unprocessable("not_scheduled", "That time isn't one of this medication's scheduled doses.")
        if status_ in ("taken", "missed") and at > now + timedelta(hours=2):
            raise _unprocessable("future_dose", "That dose isn't due yet.")
    if at < now - MAX_BACKFILL:
        raise _unprocessable("too_old", "Doses older than 30 days can't be changed.")

    dose = db.execute(select(MedicationDose).where(
        MedicationDose.medication_id == m.id, MedicationDose.scheduled_for == at,
    )).scalar_one_or_none()
    created = dose is None
    if dose is None:
        dose = MedicationDose(medication_id=m.id, user_id=user.id, scheduled_for=at, status=status_)
        db.add(dose)
    dose.status, dose.note, dose.recorded_at = status_, (note or None), now
    try:
        db.commit()
    except IntegrityError:  # a concurrent tap recorded it first; apply ours as an update
        db.rollback()
        return record_dose(db, user, m, scheduled_for, status_, note)
    return dose, created


def clear_dose(db: Session, m: Medication, scheduled_for: datetime) -> None:
    at = scheduled_for.astimezone(timezone.utc).replace(microsecond=0)
    db.execute(delete(MedicationDose).where(MedicationDose.medication_id == m.id, MedicationDose.scheduled_for == at))
    db.commit()


def _doses_between(db: Session, user: User, start: datetime, end: datetime) -> list[MedicationDose]:
    return list(db.execute(select(MedicationDose).where(
        MedicationDose.user_id == user.id, MedicationDose.scheduled_for >= start, MedicationDose.scheduled_for < end,
    )).scalars())


def _check_range(first: date, last: date) -> None:
    if last < first:
        raise _unprocessable("invalid_range", "'from' must be on or before 'to'.")
    if (last - first).days + 1 > MAX_RANGE_DAYS:
        raise _unprocessable("range_too_large", f"At most {MAX_RANGE_DAYS} days per request.")


def scheduled_doses(db: Session, user: User, first: date, last: date) -> list[ScheduledDose]:
    """Every scheduled dose in the range plus recorded as-needed doses, oldest first."""
    _check_range(first, last)
    meds = list_medications(db, user)
    now = utcnow()
    window_start, window_end = _utc_window(first, last)
    recorded = {(d.medication_id, as_utc(d.scheduled_for)): d for d in _doses_between(db, user, window_start, window_end)}
    out: list[ScheduledDose] = []
    for m in meds:
        if m.schedule_type == "as_needed":
            for (mid, at), d in recorded.items():
                if mid == m.id:
                    out.append(_scheduled(m, at, d, now))
            continue
        for at in occurrences(schedule_of(m), first, last):
            out.append(_scheduled(m, at, recorded.get((m.id, at)), now))
    out.sort(key=lambda d: (d.scheduled_for, d.medication_name))
    return out


def _utc_window(first: date, last: date) -> tuple[datetime, datetime]:
    # Generous UTC window (±14 h covers every zone); exact filtering happens per medication.
    start = datetime.combine(first, datetime.min.time(), timezone.utc) - timedelta(hours=14)
    end = datetime.combine(last + timedelta(days=1), datetime.min.time(), timezone.utc) + timedelta(hours=14)
    return start, end


def _scheduled(m: Medication, at: datetime, dose: MedicationDose | None, now: datetime) -> ScheduledDose:
    if dose is not None:
        state = dose.status
    else:
        state = "upcoming" if at > now else "unrecorded"
    return ScheduledDose(
        medication_id=m.id, medication_name=m.name, dosage_instructions=m.dosage_instructions, scheduled_for=at,
        status=state, recorded_at=as_utc(dose.recorded_at) if dose else None, note=dose.note if dose else None,
    )


def adherence(db: Session, user: User, first: date, last: date) -> list[AdherenceRow]:
    """Per-medication counts. Adherence = taken / doses that were due; unrecorded counts as not taken
    but is reported separately, so "forgot to log" is never mislabelled as "missed"."""
    meds = list_medications(db, user)
    rows = {m.id: AdherenceRow(medication_id=m.id, medication_name=m.name, scheduled=0, taken=0, skipped=0,
                               missed=0, unrecorded=0, as_needed_taken=0, adherence=None) for m in meds}
    as_needed = {m.id for m in meds if m.schedule_type == "as_needed"}
    for d in scheduled_doses(db, user, first, last):
        r = rows[d.medication_id]
        if d.medication_id in as_needed:
            r.as_needed_taken += 1
        elif d.status != "upcoming":  # not due yet: doesn't count either way
            r.scheduled += 1
            setattr(r, d.status, getattr(r, d.status) + 1)
    for r in rows.values():
        r.adherence = round(r.taken / r.scheduled, 4) if r.scheduled else None
    active = {m.id for m in meds if m.discontinued_at is None}
    return [r for r in rows.values() if r.scheduled or r.as_needed_taken or r.medication_id in active]
