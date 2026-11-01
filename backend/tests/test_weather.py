"""Weather. OpenWeather is replaced by a fake; tests never call the real API."""

import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.billing import SubscriptionEntitlement
from app.models.integrations import WeatherCache
from app.services import weather
from app.services.weather import WeatherUnavailable
from app.services.weather_rules import condition_group, outdoor_rating, round_coord

API = "/api/v1"


# ---------------------------------------------------------------- rules (pure)

def rate(**kw):
    base = dict(feels_like_c=18, wind_mps=3, pop=0.0, rain_mm=0.0, condition_code=800, is_day=True)
    return outdoor_rating(**{**base, **kw})


def test_outdoor_rating():
    assert rate() == {"score": 100, "label": "good", "reasons": ["Great conditions"]}
    assert rate(condition_code=211)["label"] == "poor"  # thunderstorm always poor
    assert rate(condition_code=501, rain_mm=4)["label"] == "fair"
    assert rate(feels_like_c=37)["label"] == "fair" and "Dangerously hot" in rate(feels_like_c=37)["reasons"]
    hot_wet_windy = rate(feels_like_c=36, condition_code=502, rain_mm=6, wind_mps=15)
    assert hot_wet_windy["score"] == 0 and hot_wet_windy["label"] == "poor"
    assert rate(is_day=False)["score"] == 85
    assert rate(pop=0.4)["reasons"] == ["Chance of rain"]


def test_condition_groups_and_rounding():
    assert [condition_group(c) for c in (200, 301, 500, 600, 741, 800, 803)] == [0, 1, 2, 3, 4, 5, 6]
    assert round_coord(-26.204103) == -26.2 and round_coord(28.047305) == 28.05


# ---------------------------------------------------------------- API with a fake provider

def ow_current(temp=22.0, code=800, now=None):
    now = now or int(time.time())
    return {"dt": now, "name": "Johannesburg", "main": {"temp": temp, "feels_like": temp, "humidity": 40},
            "wind": {"speed": 3.0}, "weather": [{"id": code, "main": "Clear", "description": "clear sky", "icon": "01d"}],
            "sys": {"sunrise": now - 3600, "sunset": now + 3600}}


def ow_forecast(now=None):
    now = now or int(time.time())
    items = []
    for i in range(16):  # 48 h of 3-hour steps
        code = 211 if i == 2 else 800
        items.append({"dt": now + i * 3 * 3600, "main": {"temp": 20 + i % 5, "feels_like": 20 + i % 5, "humidity": 50},
                      "wind": {"speed": 4}, "pop": 0.9 if i == 2 else 0.0,
                      "weather": [{"id": code, "main": "x", "description": "x", "icon": "01d"}],
                      "sys": {"pod": "d" if i % 4 in (0, 1) else "n"}})
    return {"city": {"sunrise": now - 3600, "sunset": now + 6 * 3600}, "list": items}


class FakeOW:
    def __init__(self):
        self.calls: list[tuple] = []
        self.down = False
        self.temp = 22.0

    def current(self, lat, lon):
        self.calls.append(("current", lat, lon))
        if self.down:
            raise WeatherUnavailable("down")
        return ow_current(self.temp)

    def forecast(self, lat, lon):
        self.calls.append(("forecast", lat, lon))
        if self.down:
            raise WeatherUnavailable("down")
        return ow_forecast()

    def geocode(self, q):
        self.calls.append(("geo", q))
        return [{"name": "Cape Town", "state": "Western Cape", "country": "ZA", "lat": -33.924869, "lon": 18.424055}]


@pytest.fixture
def ow(monkeypatch):
    fake = FakeOW()
    monkeypatch.setattr(weather, "get_client", lambda: fake)
    return fake


def set_location(client, h, lat=-26.204103, lon=28.047305, name="Home"):
    return client.put(f"{API}/me/weather-location", headers=h, json={"lat": lat, "lon": lon, "name": name})


def test_location_is_stored_rounded_and_can_be_deleted(client, verified):
    h, _ = verified
    assert client.get(f"{API}/weather/current", headers=h).json()["error"]["code"] == "no_location"
    saved = set_location(client, h).json()
    assert saved == {"lat": -26.2, "lon": 28.05, "name": "Home"}
    assert client.delete(f"{API}/me/weather-location", headers=h).status_code == 204
    assert client.get(f"{API}/me/weather-location", headers=h).json() == {"lat": None, "lon": None, "name": None}


def test_current_is_free_cached_and_uses_rounded_coords(client, verified, ow, db_factory):
    h, _ = verified
    set_location(client, h)
    r = client.get(f"{API}/weather/current", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["temp_c"] == 22.0 and body["outdoor"]["label"] == "good" and body["place_name"] == "Home"
    assert body["is_day"] is True and body["stale"] is False and body["hydration_tip"] is None
    client.get(f"{API}/weather/current", headers=h)
    assert ow.calls == [("current", -26.2, 28.05)]  # second call served from cache, provider saw rounded coords
    # Precise ad-hoc coordinates are rounded too and never saved to the profile.
    client.get(f"{API}/weather/current", headers=h, params={"lat": -33.92487, "lon": 18.42406})
    assert ow.calls[-1] == ("current", -33.92, 18.42)
    assert client.get(f"{API}/me/weather-location", headers=h).json()["lat"] == -26.2
    with db_factory() as db:
        keys = {r.key for r in db.execute(select(WeatherCache)).scalars()}
    assert keys == {"current:-26.20:28.05", "current:-33.92:18.42"}


def test_hot_weather_adds_a_hydration_tip(client, verified, ow):
    h, _ = verified
    ow.temp = 33.0
    r = client.get(f"{API}/weather/current", headers=h, params={"lat": 1, "lon": 2}).json()
    assert r["hydration_tip"] and r["outdoor"]["label"] == "good"  # 30–35 °C is "hot", not prohibitive
    assert "Hot — take water" in r["outdoor"]["reasons"]


def test_outage_serves_stale_cache_then_503(client, verified, ow, db_factory):
    h, _ = verified
    client.get(f"{API}/weather/current", headers=h, params={"lat": 1, "lon": 2})
    with db_factory() as db:  # cache expired
        row = db.execute(select(WeatherCache)).scalar_one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    ow.down = True
    r = client.get(f"{API}/weather/current", headers=h, params={"lat": 1, "lon": 2})
    assert r.status_code == 200 and r.json()["stale"] is True
    with db_factory() as db:  # too old to serve
        row = db.execute(select(WeatherCache)).scalar_one()
        row.fetched_at = datetime.now(timezone.utc) - timedelta(hours=7)
        db.commit()
    r = client.get(f"{API}/weather/current", headers=h, params={"lat": 1, "lon": 2})
    assert r.status_code == 503 and r.json()["error"]["code"] == "weather_unavailable"


def test_missing_api_key_is_a_clean_503(client, verified):
    h, _ = verified
    r = client.get(f"{API}/weather/current", headers=h, params={"lat": 1, "lon": 2})
    assert r.status_code == 503


def test_forecast_is_premium_and_rates_each_step(client, verified, ow, db_factory):
    h, s = verified
    set_location(client, h)
    assert client.get(f"{API}/weather/forecast", headers=h).status_code == 402
    with db_factory() as db:
        db.add(SubscriptionEntitlement(user_id=uuid.UUID(s["user"]["id"]), status="active", expires_at=None))
        db.commit()
    f = client.get(f"{API}/weather/forecast", headers=h, params={"hours": 24}).json()
    assert 1 <= len(f["steps"]) <= 9
    storm = [st for st in f["steps"] if st["condition"]["code"] == 211]
    assert storm and storm[0]["outdoor"]["label"] == "poor"
    assert f["best_time"] is not None
    best = next(st for st in f["steps"] if st["at"] == f["best_time"])
    assert best["is_day"] and best["outdoor"]["label"] != "poor"


def test_place_search_and_validation(client, verified, ow):
    h, _ = verified
    places = client.get(f"{API}/weather/places", headers=h, params={"q": "Cape Town"}).json()
    assert places == [{"name": "Cape Town, Western Cape, ZA", "lat": -33.92, "lon": 18.42}]
    assert client.get(f"{API}/weather/places", headers=h, params={"q": "x"}).status_code == 422
    assert client.get(f"{API}/weather/current", headers=h, params={"lat": 1}).status_code == 422
    assert client.get(f"{API}/weather/current", headers=h, params={"lat": 100, "lon": 0}).status_code == 422
    assert client.get(f"{API}/weather/current", params={"lat": 1, "lon": 2}).status_code == 401
