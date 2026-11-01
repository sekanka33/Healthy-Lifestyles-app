"""Pure weather logic: normalising OpenWeather payloads and rating conditions for outdoor exercise.
No I/O, so it is unit-tested directly and reused by the recommendation engine (Phase 9)."""

from datetime import datetime, timezone

# OpenWeather condition id groups: https://openweathermap.org/weather-conditions
THUNDER, DRIZZLE, RAIN, SNOW, ATMOSPHERE, CLEAR, CLOUDS = range(7)


def condition_group(code: int) -> int:
    if 200 <= code < 300:
        return THUNDER
    if 300 <= code < 400:
        return DRIZZLE
    if 500 <= code < 600:
        return RAIN
    if 600 <= code < 700:
        return SNOW
    if 700 <= code < 800:
        return ATMOSPHERE
    return CLEAR if code == 800 else CLOUDS


def _ts(epoch: int | float | None) -> datetime | None:
    return datetime.fromtimestamp(epoch, tz=timezone.utc) if epoch is not None else None


def _condition(item: dict) -> dict:
    w = (item.get("weather") or [{}])[0]
    return {"code": int(w.get("id", 800)), "main": w.get("main", "Clear"),
            "description": w.get("description", ""), "icon": w.get("icon", "01d")}


def normalise_current(raw: dict) -> dict:
    main, wind, sys = raw.get("main", {}), raw.get("wind", {}), raw.get("sys", {})
    observed = _ts(raw.get("dt"))
    sunrise, sunset = _ts(sys.get("sunrise")), _ts(sys.get("sunset"))
    return {
        "observed_at": observed,
        "temp_c": main.get("temp"),
        "feels_like_c": main.get("feels_like"),
        "humidity": main.get("humidity"),
        "wind_mps": wind.get("speed"),
        "wind_gust_mps": wind.get("gust"),
        "rain_mm_1h": (raw.get("rain") or {}).get("1h", 0.0),
        "condition": _condition(raw),
        "sunrise": sunrise,
        "sunset": sunset,
        "is_day": bool(sunrise and sunset and observed and sunrise <= observed < sunset),
        "place_name": raw.get("name") or None,
    }


def normalise_forecast(raw: dict) -> tuple[list[dict], datetime | None, datetime | None]:
    """5-day / 3-hour forecast → list of steps, plus today's sunrise/sunset."""
    city = raw.get("city", {})
    sunrise, sunset = _ts(city.get("sunrise")), _ts(city.get("sunset"))
    steps = []
    for item in raw.get("list", []):
        main, wind = item.get("main", {}), item.get("wind", {})
        steps.append({
            "at": _ts(item.get("dt")),
            "temp_c": main.get("temp"),
            "feels_like_c": main.get("feels_like"),
            "humidity": main.get("humidity"),
            "wind_mps": wind.get("speed"),
            "pop": item.get("pop", 0.0),  # probability of precipitation 0..1
            "rain_mm": (item.get("rain") or {}).get("3h", 0.0) + (item.get("snow") or {}).get("3h", 0.0),
            "condition": _condition(item),
            "is_day": (item.get("sys") or {}).get("pod", "d") == "d",
        })
    return steps, sunrise, sunset


def outdoor_rating(*, feels_like_c: float | None, wind_mps: float | None, pop: float, rain_mm: float,
                   condition_code: int, is_day: bool) -> dict:
    """Score 0–100 for walking/running outside, with plain-language reasons. Not medical advice."""
    score, reasons = 100, []
    group = condition_group(condition_code)
    if group == THUNDER:
        return {"score": 0, "label": "poor", "reasons": ["Thunderstorms — stay indoors"]}
    if group == SNOW:
        score -= 45
        reasons.append("Snow or ice")
    if group == RAIN or rain_mm >= 2:
        score -= 40 if rain_mm >= 2 else 25
        reasons.append("Rain")
    elif group == DRIZZLE or pop >= 0.6:
        score -= 20
        reasons.append("Likely showers")
    elif pop >= 0.3:
        score -= 8
        reasons.append("Chance of rain")
    if group == ATMOSPHERE:
        score -= 20
        reasons.append("Fog, haze or dust")
    if feels_like_c is not None:
        if feels_like_c >= 35:
            score -= 50
            reasons.append("Dangerously hot")
        elif feels_like_c >= 30:
            score -= 25
            reasons.append("Hot — take water")
        elif feels_like_c <= -5:
            score -= 40
            reasons.append("Very cold")
        elif feels_like_c <= 3:
            score -= 15
            reasons.append("Cold — dress warmly")
    if wind_mps is not None:
        if wind_mps >= 14:
            score -= 35
            reasons.append("Very windy")
        elif wind_mps >= 9:
            score -= 15
            reasons.append("Windy")
    if not is_day:
        score -= 15
        reasons.append("Dark — wear something visible")
    score = max(0, min(100, score))
    label = "good" if score >= 70 else "fair" if score >= 40 else "poor"
    if not reasons:
        reasons.append("Great conditions")
    return {"score": score, "label": label, "reasons": reasons}


def hydration_tip(feels_like_c: float | None, humidity: float | None) -> str | None:
    if feels_like_c is None:
        return None
    if feels_like_c >= 30:
        return "It's hot out — sip water regularly, especially if you're active."
    if feels_like_c >= 26 and (humidity or 0) >= 60:
        return "Warm and humid today — keep your water bottle close."
    return None


def round_coord(value: float) -> float:
    """~1.1 km precision: enough for weather, far less revealing than a GPS fix."""
    return round(value, 2)
