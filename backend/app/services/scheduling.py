"""Free-time and recommendation engine. Pure functions — no I/O, fully unit-tested.

Free slots = the waking part of a local day, minus calendar busy blocks, minus the past.
Recommendations are built from those slots:
- hydration breaks (every plan), spaced out across the day;
- walks / jogs / runs (Premium), outside working hours, scored by the weather forecast and the
  user's preferred time of day. A slot whose weather is "poor" is never suggested for outdoor exercise.
The engine is deliberately rule-based: deterministic, explainable ("why this time?"), easy to extend.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.services.weather_rules import outdoor_rating


@dataclass(frozen=True, order=True)
class Interval:
    start: datetime
    end: datetime

    @property
    def minutes(self) -> float:
        return (self.end - self.start).total_seconds() / 60


@dataclass
class Suggestion:
    kind: str  # "hydration" | "walking" | "jogging" | "running"
    title: str
    reason: str
    slot: Interval
    start: datetime
    end: datetime
    score: float = 0.0
    weather: dict | None = field(default=None)


ACTIVITY_MINUTES = {"walking": 30, "jogging": 30, "running": 30}
ACTIVITY_TITLE = {"walking": "Go for a walk", "jogging": "Go for a jog", "running": "Go for a run"}
TIME_BANDS = {"morning": (5, 12), "afternoon": (12, 17), "evening": (17, 22)}
MAX_HYDRATION = 4
HYDRATION_SPACING = timedelta(minutes=90)
MAX_ACTIVITIES = 3


def merge(intervals: list[Interval]) -> list[Interval]:
    out: list[Interval] = []
    for iv in sorted(i for i in intervals if i.end > i.start):
        if out and iv.start <= out[-1].end:
            out[-1] = Interval(out[-1].start, max(out[-1].end, iv.end))
        else:
            out.append(iv)
    return out


def subtract(base: Interval, busy: list[Interval]) -> list[Interval]:
    free, cursor = [], base.start
    for b in merge(busy):
        if b.end <= cursor or b.start >= base.end:
            continue
        if b.start > cursor:
            free.append(Interval(cursor, min(b.start, base.end)))
        cursor = max(cursor, b.end)
        if cursor >= base.end:
            break
    if cursor < base.end:
        free.append(Interval(cursor, base.end))
    return free


def local_window(day: date, tz: ZoneInfo, start: time, end: time) -> Interval:
    """[start, end) on `day` in UTC. An end at/before the start runs past midnight."""
    s = datetime.combine(day, start, tz)
    e = datetime.combine(day if end > start else day + timedelta(days=1), end, tz)
    return Interval(s.astimezone(timezone.utc), e.astimezone(timezone.utc))


def free_slots(day: date, tz_name: str, busy: list[Interval], *, wake: time, sleep: time,
               min_minutes: int, now: datetime) -> list[Interval]:
    tz = ZoneInfo(tz_name)
    awake = local_window(day, tz, wake, sleep)
    if now > awake.start:
        awake = Interval(max(awake.start, now), awake.end)
    if awake.end <= awake.start:
        return []
    return [s for s in subtract(awake, busy) if s.minutes >= min_minutes]


def _band(at: datetime, tz: ZoneInfo) -> str | None:
    h = at.astimezone(tz).hour
    return next((name for name, (a, b) in TIME_BANDS.items() if a <= h < b), None)


def _hm(dt: datetime, tz: ZoneInfo) -> str:
    return dt.astimezone(tz).strftime("%H:%M")


def _weather_at(steps: list[dict], at: datetime) -> dict | None:
    """Forecast step covering `at` (3-hour steps)."""
    for s in steps:
        if s["at"] <= at < s["at"] + timedelta(hours=3):
            return s
    return None


def recommend(slots: list[Interval], *, tz_name: str, premium: bool, forecast: list[dict] | None,
              preferred_activities: list[str], preferred_times: list[str],
              working: Interval | None) -> tuple[list[Suggestion], int]:
    """Returns (suggestions sorted by time, number of activity ideas withheld for the Free plan)."""
    tz = ZoneInfo(tz_name)
    out: list[Suggestion] = []

    # Hydration breaks: the start of free slots, at least 90 minutes apart.
    last: datetime | None = None
    for s in slots:
        if len([x for x in out if x.kind == "hydration"]) >= MAX_HYDRATION:
            break
        if last is None or s.start - last >= HYDRATION_SPACING:
            out.append(Suggestion(
                kind="hydration", title="Water break", slot=s, start=s.start, end=s.start + timedelta(minutes=5),
                reason=f"You're free {_hm(s.start, tz)}–{_hm(s.end, tz)}. A glass of water now keeps you on track.",
            ))
            last = s.start

    # Outdoor activity: best start time in each slot outside working hours.
    activities = [a for a in preferred_activities if a in ACTIVITY_MINUTES] or ["walking"]
    candidates: list[Suggestion] = []
    for s in slots:
        pieces = subtract(s, [working]) if working else [s]
        for piece in pieces:
            for activity in activities:
                need = timedelta(minutes=ACTIVITY_MINUTES[activity])
                t = piece.start
                best: Suggestion | None = None
                while t + need <= piece.end:
                    w = _weather_at(forecast, t) if forecast else None
                    rating = (outdoor_rating(feels_like_c=w["feels_like_c"], wind_mps=w["wind_mps"],
                                             pop=w.get("pop") or 0.0, rain_mm=w.get("rain_mm") or 0.0,
                                             condition_code=w["condition"]["code"], is_day=w["is_day"])
                              if w else None)
                    if rating is None or rating["label"] != "poor":
                        score = (rating["score"] if rating else 60) + (15 if _band(t, tz) in preferred_times else 0)
                        if best is None or score > best.score:
                            why = f"Free {_hm(piece.start, tz)}–{_hm(piece.end, tz)}"
                            if w and rating:
                                why += f" · {round(w['temp_c'])}°C, {', '.join(rating['reasons']).lower()}"
                            else:
                                why += " · no forecast for this time"
                            if _band(t, tz) in preferred_times:
                                why += f" · your preferred {_band(t, tz)} time"
                            best = Suggestion(kind=activity, title=ACTIVITY_TITLE[activity], slot=piece, start=t,
                                              end=t + need, score=score, reason=why,
                                              weather={"temp_c": w["temp_c"], "condition": w["condition"], "outdoor": rating}
                                              if w and rating else None)
                    t += timedelta(minutes=30)
                if best:
                    candidates.append(best)

    # Keep the strongest, non-overlapping ideas.
    chosen: list[Suggestion] = []
    for c in sorted(candidates, key=lambda c: (-c.score, c.start)):
        if len(chosen) >= MAX_ACTIVITIES:
            break
        if all(c.end <= x.start or c.start >= x.end for x in chosen):
            chosen.append(c)
    withheld = 0
    if premium:
        out.extend(chosen)
    else:
        withheld = len(chosen)
    return sorted(out, key=lambda x: (x.start, x.kind)), withheld
