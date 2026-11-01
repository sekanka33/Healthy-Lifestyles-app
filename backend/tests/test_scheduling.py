from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.services.scheduling import Interval, free_slots, local_window, merge, recommend, subtract

TZ = "Africa/Johannesburg"  # UTC+2, no DST
JHB = ZoneInfo(TZ)
DAY = date(2026, 11, 2)
EARLY = datetime(2026, 11, 1, tzinfo=timezone.utc)  # "now" before the day starts


def at(h, m=0, day=DAY):
    return datetime.combine(day, time(h, m), JHB).astimezone(timezone.utc)


def test_merge_and_subtract():
    a = [Interval(at(9), at(10)), Interval(at(9, 30), at(11)), Interval(at(13), at(14))]
    assert merge(a) == [Interval(at(9), at(11)), Interval(at(13), at(14))]
    assert subtract(Interval(at(8), at(15)), a) == [Interval(at(8), at(9)), Interval(at(11), at(13)), Interval(at(14), at(15))]


def test_free_slots_respect_waking_hours_minimum_and_now():
    busy = [Interval(at(9), at(12)), Interval(at(12, 10), at(17))]
    slots = free_slots(DAY, TZ, busy, wake=time(6, 30), sleep=time(22), min_minutes=15, now=EARLY)
    assert slots == [Interval(at(6, 30), at(9)), Interval(at(17), at(22))]  # 10-minute gap dropped
    later = free_slots(DAY, TZ, busy, wake=time(6, 30), sleep=time(22), min_minutes=15, now=at(18))
    assert later == [Interval(at(18), at(22))]


def test_window_that_crosses_midnight():
    w = local_window(DAY, JHB, time(22), time(2))
    assert w.end - w.start == timedelta(hours=4)


def fc(hours_good: dict[int, int]) -> list[dict]:
    """Forecast for DAY: {local_hour: condition_code}, 3-hour steps."""
    return [{"at": at(h), "temp_c": 20, "feels_like_c": 20, "wind_mps": 3, "pop": 0.0, "rain_mm": 0.0,
             "condition": {"code": code, "main": "", "description": "", "icon": ""}, "is_day": 6 <= h < 19}
            for h, code in hours_good.items()]


def test_hydration_breaks_are_spaced_and_capped():
    slots = [Interval(at(h), at(h, 30)) for h in (7, 8, 9, 11, 13, 15, 17)]
    recs, _ = recommend(slots, tz_name=TZ, premium=False, forecast=None, preferred_activities=[],
                        preferred_times=[], working=None)
    starts = [r.start for r in recs if r.kind == "hydration"]
    assert len(starts) == 4
    assert all(b - a >= timedelta(minutes=90) for a, b in zip(starts, starts[1:]))


def test_free_plan_gets_no_activity_ideas_but_knows_how_many_exist():
    slots = [Interval(at(17), at(19))]
    recs, withheld = recommend(slots, tz_name=TZ, premium=False, forecast=fc({15: 800, 18: 800}),
                               preferred_activities=["running"], preferred_times=[], working=None)
    assert all(r.kind == "hydration" for r in recs) and withheld == 1


def test_premium_activity_avoids_storms_work_and_prefers_chosen_time():
    slots = [Interval(at(7), at(9)), Interval(at(12), at(13)), Interval(at(18), at(19))]
    forecast = fc({6: 211, 12: 800, 15: 800, 18: 800})  # thunderstorm all morning
    work = Interval(at(8), at(17))
    recs, withheld = recommend(slots, tz_name=TZ, premium=True, forecast=forecast,
                               preferred_activities=["walking"], preferred_times=["evening"], working=work)
    walks = [r for r in recs if r.kind == "walking"]
    assert withheld == 0
    assert [w.start for w in walks] == [at(18)]  # morning stormy, lunch inside work hours
    assert "preferred evening" in walks[0].reason and walks[0].weather["outdoor"]["label"] == "good"


def test_activity_without_forecast_still_suggested_but_says_so():
    recs, _ = recommend([Interval(at(17), at(18))], tz_name=TZ, premium=True, forecast=None,
                        preferred_activities=["jogging"], preferred_times=[], working=None)
    jog = next(r for r in recs if r.kind == "jogging")
    assert "no forecast" in jog.reason and jog.end - jog.start == timedelta(minutes=30)


def test_suggestions_never_overlap_and_are_capped():
    slots = [Interval(at(h), at(h + 1)) for h in (6, 8, 10, 14, 16, 18)]
    recs, _ = recommend(slots, tz_name=TZ, premium=True, forecast=None,
                        preferred_activities=["walking", "running"], preferred_times=[], working=None)
    acts = sorted((r for r in recs if r.kind != "hydration"), key=lambda r: r.start)
    assert len(acts) == 3
    assert all(a.end <= b.start for a, b in zip(acts, acts[1:]))
