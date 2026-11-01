"""Weather via OpenWeather, proxied by the backend.

- The API key never ships in the app.
- Coordinates are rounded to 2 dp (~1 km) before they are used, cached or stored, and never logged.
- Responses are cached per rounded location (current: 10 min, forecast: 30 min), which keeps us well
  inside the free tier. If OpenWeather is down we serve the last cached copy (marked `stale`) for up
  to 6 hours rather than fail.
Uses the free-plan endpoints: /data/2.5/weather, /data/2.5/forecast and /geo/1.0/direct.
"""

import logging
from datetime import timedelta

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import as_utc, utcnow
from app.models.integrations import WeatherCache
from app.services.weather_rules import (
    hydration_tip,
    normalise_current,
    normalise_forecast,
    outdoor_rating,
    round_coord,
)

logger = logging.getLogger("app.weather")

BASE = "https://api.openweathermap.org"
TTL = {"current": timedelta(minutes=10), "forecast": timedelta(minutes=30), "geo": timedelta(days=7)}
STALE_LIMIT = timedelta(hours=6)


class WeatherUnavailable(Exception):
    pass


class OpenWeatherClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def _get(self, path: str, params: dict) -> dict | list:
        try:
            res = httpx.get(f"{BASE}{path}", params={**params, "appid": self.api_key}, timeout=10)
        except httpx.HTTPError as exc:
            raise WeatherUnavailable(type(exc).__name__) from exc
        if res.status_code != 200:
            raise WeatherUnavailable(f"HTTP {res.status_code}")
        return res.json()

    def current(self, lat: float, lon: float) -> dict:
        return self._get("/data/2.5/weather", {"lat": lat, "lon": lon, "units": "metric"})

    def forecast(self, lat: float, lon: float) -> dict:
        return self._get("/data/2.5/forecast", {"lat": lat, "lon": lon, "units": "metric"})

    def geocode(self, query: str) -> list:
        return self._get("/geo/1.0/direct", {"q": query, "limit": 5})


def get_client() -> OpenWeatherClient:
    key = get_settings().openweather_api_key
    if not key:
        raise WeatherUnavailable("OPENWEATHER_API_KEY is not configured")
    return OpenWeatherClient(key)


def _unavailable() -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                         {"code": "weather_unavailable", "message": "Weather is unavailable right now. Try again soon."})


def _cached(db: Session, key: str, kind: str, fetch) -> tuple[dict | list, bool]:
    """Returns (payload, stale). Fresh cache → payload; else fetch; on failure fall back to stale cache."""
    now = utcnow()
    row = db.get(WeatherCache, key)
    if row is not None and as_utc(row.expires_at) > now:
        return row.payload, False
    try:
        payload = fetch()
    except WeatherUnavailable as exc:
        logger.warning("Weather fetch failed (%s): %s", kind, exc)
        if row is not None and now - as_utc(row.fetched_at) <= STALE_LIMIT:
            return row.payload, True
        raise _unavailable() from None
    if row is None:
        row = WeatherCache(key=key, fetched_at=now, expires_at=now + TTL[kind], payload=payload)
        db.add(row)
    else:
        row.fetched_at, row.expires_at, row.payload = now, now + TTL[kind], payload
    db.commit()
    return payload, False


def current(db: Session, lat: float, lon: float) -> dict:
    lat, lon = round_coord(lat), round_coord(lon)
    raw, stale = _cached(db, f"current:{lat:.2f}:{lon:.2f}", "current", lambda: get_client().current(lat, lon))
    c = normalise_current(raw)
    c["outdoor"] = outdoor_rating(feels_like_c=c["feels_like_c"], wind_mps=c["wind_mps"], pop=0.0,
                                  rain_mm=c["rain_mm_1h"] or 0.0, condition_code=c["condition"]["code"],
                                  is_day=c["is_day"])
    c["hydration_tip"] = hydration_tip(c["feels_like_c"], c["humidity"])
    c.update(lat=lat, lon=lon, stale=stale)
    return c


def forecast(db: Session, lat: float, lon: float, hours: int = 48) -> dict:
    lat, lon = round_coord(lat), round_coord(lon)
    raw, stale = _cached(db, f"forecast:{lat:.2f}:{lon:.2f}", "forecast", lambda: get_client().forecast(lat, lon))
    steps, sunrise, sunset = normalise_forecast(raw)
    now = utcnow()
    horizon = now + timedelta(hours=hours)
    out = []
    for s in steps:
        if s["at"] is None or s["at"] + timedelta(hours=3) <= now or s["at"] > horizon:
            continue
        s["outdoor"] = outdoor_rating(feels_like_c=s["feels_like_c"], wind_mps=s["wind_mps"], pop=s["pop"] or 0.0,
                                      rain_mm=s["rain_mm"] or 0.0, condition_code=s["condition"]["code"],
                                      is_day=s["is_day"])
        out.append(s)
    best = max((s for s in out if s["is_day"] and s["at"] >= now - timedelta(hours=1)),
               key=lambda s: s["outdoor"]["score"], default=None)
    return {"lat": lat, "lon": lon, "stale": stale, "sunrise": sunrise, "sunset": sunset, "steps": out,
            "best_time": best["at"] if best and best["outdoor"]["label"] != "poor" else None}


def search_places(db: Session, query: str) -> list[dict]:
    q = " ".join(query.split())[:100]
    raw, _ = _cached(db, f"geo:{q.lower()}"[:100], "geo", lambda: get_client().geocode(q))
    places = []
    for p in raw if isinstance(raw, list) else []:
        parts = [p.get("name"), p.get("state"), p.get("country")]
        places.append({"name": ", ".join(x for x in parts if x), "lat": round_coord(p["lat"]), "lon": round_coord(p["lon"])})
    return places
