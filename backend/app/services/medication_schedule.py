"""Turns a medication schedule into concrete dose times. Pure functions — no database.

Times are wall-clock times in the medication's own IANA zone ("08:00 in Africa/Johannesburg"), so a
dose stays at 08:00 local across DST changes. Edge cases:
- a time that doesn't exist on a spring-forward day (02:30 when clocks jump 02:00 → 03:00) is moved
  forward by the gap (→ 03:30), never dropped;
- a time that happens twice on a fall-back day uses the first occurrence (one dose, not two).
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

SCHEDULE_TYPES = ("daily", "specific_days", "every_n_days", "as_needed")


@dataclass(frozen=True)
class Schedule:
    schedule_type: str
    times: list[str]  # "HH:MM"
    timezone: str
    start_date: date
    end_date: date | None = None
    days_of_week: list[int] | None = None  # ISO 1 = Monday … 7 = Sunday
    interval_days: int | None = None
    discontinued_at: datetime | None = None


def parse_hhmm(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


def local_to_utc(day: date, t: time, tz: ZoneInfo) -> datetime:
    # fold=0 (PEP 495): a non-existent time is read with the pre-transition offset, which lands on
    # the shifted-forward instant (02:30 → 03:30); an ambiguous time resolves to its first occurrence.
    return datetime.combine(day, t).replace(tzinfo=tz, fold=0).astimezone(timezone.utc)


def is_due_on(s: Schedule, day: date) -> bool:
    if day < s.start_date or (s.end_date is not None and day > s.end_date):
        return False
    if s.schedule_type == "daily":
        return True
    if s.schedule_type == "specific_days":
        return day.isoweekday() in (s.days_of_week or [])
    if s.schedule_type == "every_n_days":
        n = s.interval_days or 1
        return (day - s.start_date).days % n == 0
    return False  # as_needed has no scheduled doses


def occurrences(s: Schedule, first_day: date, last_day: date) -> list[datetime]:
    """UTC instants of every scheduled dose on local days first_day..last_day (inclusive)."""
    tz = ZoneInfo(s.timezone)
    times = sorted({parse_hhmm(t) for t in s.times})
    out: list[datetime] = []
    day = first_day
    while day <= last_day:
        if is_due_on(s, day):
            for t in times:
                at = local_to_utc(day, t, tz)
                if s.discontinued_at is None or at < s.discontinued_at:
                    out.append(at)
        day += timedelta(days=1)
    return out


def is_occurrence(s: Schedule, at: datetime) -> bool:
    """Is `at` (UTC) exactly one of this schedule's dose times?"""
    local_day = at.astimezone(ZoneInfo(s.timezone)).date()
    return any(o == at for o in occurrences(s, local_day - timedelta(days=1), local_day + timedelta(days=1)))
