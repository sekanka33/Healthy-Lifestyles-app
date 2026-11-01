from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from app.api.deps import DB, PremiumUser, VerifiedUser
from app.core import rate_limit
from app.models.user import User, UserPreferences
from app.services import weather as svc
from app.services.weather_rules import round_coord

router = APIRouter(tags=["weather"])


class Condition(BaseModel):
    code: int
    main: str
    description: str
    icon: str


class Outdoor(BaseModel):
    score: int
    label: str  # good | fair | poor
    reasons: list[str]


class CurrentOut(BaseModel):
    lat: float
    lon: float
    place_name: str | None
    observed_at: datetime | None
    temp_c: float | None
    feels_like_c: float | None
    humidity: float | None
    wind_mps: float | None
    wind_gust_mps: float | None
    rain_mm_1h: float | None
    condition: Condition
    sunrise: datetime | None
    sunset: datetime | None
    is_day: bool
    outdoor: Outdoor
    hydration_tip: str | None
    stale: bool  # served from cache because OpenWeather was unreachable


class Step(BaseModel):
    at: datetime
    temp_c: float | None
    feels_like_c: float | None
    humidity: float | None
    wind_mps: float | None
    pop: float | None
    rain_mm: float | None
    condition: Condition
    is_day: bool
    outdoor: Outdoor


class ForecastOut(BaseModel):
    lat: float
    lon: float
    stale: bool
    sunrise: datetime | None
    sunset: datetime | None
    steps: list[Step]  # 3-hour steps
    best_time: datetime | None  # best-rated daylight slot, if any isn't "poor"


class Place(BaseModel):
    name: str
    lat: float
    lon: float


class LocationIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    name: str | None = Field(default=None, max_length=120)


class LocationOut(BaseModel):
    lat: float | None
    lon: float | None
    name: str | None


def _prefs(db, user: User) -> UserPreferences:
    p = db.get(UserPreferences, user.id)
    if p is None:
        p = UserPreferences(user_id=user.id)
        db.add(p)
        db.commit()
    return p


def _where(db, user: User, lat: float | None, lon: float | None) -> tuple[float, float, str | None]:
    if (lat is None) != (lon is None):
        raise HTTPException(422, {"code": "invalid_location", "message": "Send both lat and lon, or neither."})
    if lat is not None:
        return lat, lon, None
    p = _prefs(db, user)
    if p.weather_lat is None or p.weather_lon is None:
        raise HTTPException(status.HTTP_409_CONFLICT, {"code": "no_location", "message": "Choose a location for weather first."})
    return p.weather_lat, p.weather_lon, p.weather_location_name


Lat = Annotated[float | None, Query(ge=-90, le=90)]
Lon = Annotated[float | None, Query(ge=-180, le=180)]


@router.get("/weather/current", response_model=CurrentOut)
def current(user: VerifiedUser, db: DB, lat: Lat = None, lon: Lon = None):
    """Free. Uses the saved location unless lat/lon are given (they are rounded and not stored)."""
    rate_limit.hit(db, f"weather:user:{user.id}", limit=60, window_seconds=600)
    la, lo, name = _where(db, user, lat, lon)
    data = svc.current(db, la, lo)
    data["place_name"] = name or data["place_name"]
    return data


@router.get("/weather/forecast", response_model=ForecastOut)
def forecast(user: PremiumUser, db: DB, lat: Lat = None, lon: Lon = None,
             hours: Annotated[int, Query(ge=3, le=120)] = 48):
    """Premium. 3-hourly forecast with an outdoor-exercise rating for each step."""
    rate_limit.hit(db, f"weather:user:{user.id}", limit=60, window_seconds=600)
    la, lo, _ = _where(db, user, lat, lon)
    return svc.forecast(db, la, lo, hours)


@router.get("/weather/places", response_model=list[Place])
def places(user: VerifiedUser, db: DB, q: Annotated[str, Query(min_length=2, max_length=100)]):
    rate_limit.hit(db, f"weather-geo:user:{user.id}", limit=30, window_seconds=600)
    return svc.search_places(db, q)


@router.get("/me/weather-location", response_model=LocationOut)
def get_location(user: VerifiedUser, db: DB):
    p = _prefs(db, user)
    return LocationOut(lat=p.weather_lat, lon=p.weather_lon, name=p.weather_location_name)


@router.put("/me/weather-location", response_model=LocationOut)
def put_location(data: LocationIn, user: VerifiedUser, db: DB):
    """Stored only at ~1 km precision."""
    p = _prefs(db, user)
    p.weather_lat, p.weather_lon = round_coord(data.lat), round_coord(data.lon)
    p.weather_location_name = data.name.strip() if data.name and data.name.strip() else None
    db.commit()
    return LocationOut(lat=p.weather_lat, lon=p.weather_lon, name=p.weather_location_name)


@router.delete("/me/weather-location", status_code=status.HTTP_204_NO_CONTENT)
def delete_location(user: VerifiedUser, db: DB):
    p = _prefs(db, user)
    p.weather_lat = p.weather_lon = p.weather_location_name = None
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
