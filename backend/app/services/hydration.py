"""Hydration tracking.

Day boundaries follow the user's IANA time zone: a local day D covers the half-open UTC interval
[local midnight D, local midnight D+1), computed with zoneinfo so 23 h / 25 h DST days are exact.
Goals are versioned by `effective_from` so changing a goal never rewrites past days.
"""

import uuid
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import as_utc, utcnow
from app.models.hydration import HydrationEntry, HydrationGoal
from app.models.user import User
from app.schemas.hydration import DaySummary, EntryIn, EntryOut

DEFAULT_GOAL_ML = 2000
MAX_BACKFILL_DAYS = 7
MAX_CLOCK_SKEW = timedelta(minutes=5)
MAX_HISTORY_DAYS = 366


def _zone(user: User) -> ZoneInfo:
    return ZoneInfo(user.timezone or "UTC")


def local_today(user: User, now: datetime | None = None) -> date:
    return (now or utcnow()).astimezone(_zone(user)).date()


def day_bounds_utc(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


# ---------------------------------------------------------------- goals

def goal_rows(db: Session, user_id: uuid.UUID, up_to: date) -> list[HydrationGoal]:
    return list(db.execute(
        select(HydrationGoal).where(HydrationGoal.user_id == user_id, HydrationGoal.effective_from <= up_to)
        .order_by(HydrationGoal.effective_from)
    ).scalars())


def goal_for(rows: list[HydrationGoal], day: date) -> int:
    """`rows` sorted ascending by effective_from."""
    goal = rows[0].daily_goal_ml if rows else DEFAULT_GOAL_ML  # days before the first goal use it too
    for r in rows:
        if r.effective_from <= day:
            goal = r.daily_goal_ml
        else:
            break
    return goal


def current_goal(db: Session, user: User) -> HydrationGoal | None:
    rows = goal_rows(db, user.id, local_today(user))
    return rows[-1] if rows else None


def set_goal(db: Session, user: User, daily_goal_ml: int, *, commit: bool = True) -> HydrationGoal:
    """A goal change applies from today (local) onwards; same-day changes overwrite today's row."""
    today = local_today(user)
    row = db.execute(
        select(HydrationGoal).where(HydrationGoal.user_id == user.id, HydrationGoal.effective_from == today)
    ).scalar_one_or_none()
    if row is None:
        row = HydrationGoal(user_id=user.id, effective_from=today, daily_goal_ml=daily_goal_ml)
        db.add(row)
    else:
        row.daily_goal_ml = daily_goal_ml
    if commit:
        db.commit()
    return row


# ---------------------------------------------------------------- entries

def to_out(e: HydrationEntry) -> EntryOut:
    return EntryOut(id=e.id, client_id=e.client_id, volume_ml=e.volume_ml, consumed_at=as_utc(e.consumed_at),
                    source=e.source, deleted=e.deleted_at is not None)


def _by_client_id(db: Session, user_id: uuid.UUID, client_id: uuid.UUID) -> HydrationEntry | None:
    return db.execute(
        select(HydrationEntry).where(HydrationEntry.user_id == user_id, HydrationEntry.client_id == client_id)
    ).scalar_one_or_none()


def add_entry(db: Session, user: User, data: EntryIn) -> tuple[HydrationEntry, bool]:
    """Idempotent on client_id. Returns (entry, created)."""
    existing = _by_client_id(db, user.id, data.client_id)
    if existing is not None:
        return existing, False

    now = utcnow()
    consumed_at = data.consumed_at.astimezone(timezone.utc) if data.consumed_at else now
    if consumed_at > now + MAX_CLOCK_SKEW:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            {"code": "future_timestamp", "message": "consumed_at is in the future."})
    if consumed_at < now - timedelta(days=MAX_BACKFILL_DAYS):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            {"code": "too_old", "message": f"Entries can be back-dated at most {MAX_BACKFILL_DAYS} days."})
    entry = HydrationEntry(user_id=user.id, client_id=data.client_id, volume_ml=data.volume_ml,
                           consumed_at=min(consumed_at, now), source=data.source)
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:  # concurrent retry with the same client_id won the insert
        db.rollback()
        existing = _by_client_id(db, user.id, data.client_id)
        if existing is None:
            raise
        return existing, False
    return entry, True


def delete_entry(db: Session, user: User, client_id: uuid.UUID) -> HydrationEntry:
    """Soft delete (undo). Idempotent; 404 only if the entry never reached the server."""
    entry = _by_client_id(db, user.id, client_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, {"code": "not_found", "message": "Entry not found."})
    if entry.deleted_at is None:
        entry.deleted_at = utcnow()
        db.commit()
    return entry


def entries_between(db: Session, user_id: uuid.UUID, start: datetime, end: datetime) -> list[HydrationEntry]:
    return list(db.execute(
        select(HydrationEntry)
        .where(HydrationEntry.user_id == user_id, HydrationEntry.deleted_at.is_(None),
               HydrationEntry.consumed_at >= start, HydrationEntry.consumed_at < end)
        .order_by(HydrationEntry.consumed_at)
    ).scalars())


def _summary(day: date, total: int, goal: int) -> DaySummary:
    return DaySummary(date=day, total_ml=total, goal_ml=goal, progress=round(total / goal, 4),
                      goal_met=total >= goal)


def day_detail(db: Session, user: User, day: date) -> tuple[DaySummary, list[HydrationEntry]]:
    start, end = day_bounds_utc(day, _zone(user))
    entries = entries_between(db, user.id, start, end)
    goal = goal_for(goal_rows(db, user.id, day), day)
    return _summary(day, sum(e.volume_ml for e in entries), goal), entries


def history(db: Session, user: User, start_day: date, end_day: date) -> list[DaySummary]:
    """Inclusive range of local days, oldest first."""
    if end_day < start_day:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            {"code": "invalid_range", "message": "'from' must be on or before 'to'."})
    if (end_day - start_day).days + 1 > MAX_HISTORY_DAYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            {"code": "range_too_large", "message": f"At most {MAX_HISTORY_DAYS} days per request."})
    tz = _zone(user)
    start, _ = day_bounds_utc(start_day, tz)
    _, end = day_bounds_utc(end_day, tz)
    totals: dict[date, int] = defaultdict(int)
    for e in entries_between(db, user.id, start, end):
        totals[as_utc(e.consumed_at).astimezone(tz).date()] += e.volume_ml
    goals = goal_rows(db, user.id, end_day)
    days = []
    d = start_day
    while d <= end_day:
        days.append(_summary(d, totals.get(d, 0), goal_for(goals, d)))
        d += timedelta(days=1)
    return days
