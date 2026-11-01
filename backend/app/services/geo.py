"""GPS maths for workouts. Pure functions — no database.

Distance is computed on the server from the raw points, so a modified app can't inflate it. Points are
filtered before they count:
- poor accuracy (> MAX_ACCURACY_M) — indoor / urban-canyon fixes;
- impossible jumps (implied speed above a ceiling for the activity);
- jitter (< MIN_STEP_M from the last kept point) — standing still shouldn't add distance.
Distance never bridges segments: a pause/resume starts a new segment.
"""

import math
from dataclasses import dataclass
from datetime import datetime

EARTH_RADIUS_M = 6_371_008.8  # mean Earth radius (IUGG)
MAX_ACCURACY_M = 35.0
MIN_STEP_M = 3.0
# Generous ceilings (m/s): above these a fix is a GPS jump, not a person.
MAX_SPEED_MPS = {"walking": 3.5, "jogging": 6.0, "running": 10.0}
# Metabolic equivalents (2011 Compendium of Physical Activities, typical values).
MET = {"walking": 3.5, "jogging": 7.0, "running": 9.8}


@dataclass
class Fix:
    seq: int
    segment: int
    recorded_at: datetime
    lat: float
    lon: float
    accuracy_m: float | None = None
    accepted: bool = True


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def filter_fixes(fixes: list[Fix], activity: str) -> list[Fix]:
    """Sets `accepted` on each fix (in seq order) and returns the list."""
    ceiling = MAX_SPEED_MPS.get(activity, 10.0)
    last: Fix | None = None
    for f in sorted(fixes, key=lambda x: x.seq):
        if last is not None and f.segment != last.segment:
            last = None  # new segment after a pause: never bridge the gap
        if f.accuracy_m is not None and f.accuracy_m > MAX_ACCURACY_M:
            f.accepted = False
            continue
        if last is None:
            f.accepted, last = True, f
            continue
        dt = (f.recorded_at - last.recorded_at).total_seconds()
        d = haversine_m(last.lat, last.lon, f.lat, f.lon)
        if dt <= 0 or d / dt > ceiling or d < MIN_STEP_M:
            f.accepted = False
            continue
        f.accepted, last = True, f
    return fixes


def route_distance_m(fixes: list[Fix]) -> float:
    total, prev = 0.0, None
    for f in sorted(fixes, key=lambda x: x.seq):
        if not f.accepted:
            continue
        if prev is not None and prev.segment == f.segment:
            total += haversine_m(prev.lat, prev.lon, f.lat, f.lon)
        prev = f
    return total


def calories_estimate(activity: str, active_seconds: int, weight_kg: float | None) -> float | None:
    """kcal ≈ MET × kg × hours. Without a body weight we don't guess — return None."""
    if not weight_kg or active_seconds <= 0:
        return None
    return round(MET.get(activity, 3.5) * weight_kg * active_seconds / 3600, 1)


def pace_s_per_km(distance_m: float, active_seconds: int) -> float | None:
    if distance_m < 10 or active_seconds <= 0:
        return None
    return active_seconds / (distance_m / 1000)
