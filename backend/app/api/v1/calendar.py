import uuid
from datetime import date, datetime, time
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator

from app.api.deps import DB, PremiumUser, VerifiedUser
from app.core import rate_limit
from app.db.base import as_utc
from app.models.integrations import ActivityRecommendation
from app.services import calendar as svc
from app.services import google_calendar as google
from app.services.hydration import local_today

router = APIRouter(tags=["calendar"])


class CalendarStatus(BaseModel):
    connected: bool
    status: str | None  # active | revoked | error
    can_read_free_busy: bool
    can_add_events: bool


class AuthUrl(BaseModel):
    auth_url: str


class Slot(BaseModel):
    start: datetime
    end: datetime
    minutes: int


class FreeSlots(BaseModel):
    date: date
    timezone: str
    calendar_used: bool  # false = no calendar connected, the whole waking day counts as free
    slots: list[Slot]


class Recommendation(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    reason: str
    start: datetime
    end: datetime
    status: str
    weather: dict | None


class Recommendations(BaseModel):
    date: date
    timezone: str
    calendar_used: bool
    items: list[Recommendation]
    premium_ideas_available: int  # activity ideas withheld on the Free plan


class SchedulingPrefs(BaseModel):
    working_hours_start: time | None
    working_hours_end: time | None
    sleep_start: time
    sleep_end: time
    min_free_slot_minutes: int
    preferred_activities: list[Literal["walking", "jogging", "running"]]
    preferred_activity_times: list[Literal["morning", "afternoon", "evening"]]


class SchedulingPrefsIn(BaseModel):
    working_hours_start: time | None = None
    working_hours_end: time | None = None
    sleep_start: time | None = None
    sleep_end: time | None = None
    min_free_slot_minutes: int | None = Field(default=None, ge=10, le=120)
    preferred_activities: list[Literal["walking", "jogging", "running"]] | None = Field(default=None, max_length=3)
    preferred_activity_times: list[Literal["morning", "afternoon", "evening"]] | None = Field(default=None, max_length=3)

    @field_validator("preferred_activities", "preferred_activity_times")
    @classmethod
    def dedupe(cls, v):
        return sorted(set(v)) if v is not None else v


def _rec_out(r: ActivityRecommendation) -> Recommendation:
    return Recommendation(id=r.id, kind=r.kind, title=r.title, reason=r.reason, start=as_utc(r.suggested_start),
                          end=as_utc(r.suggested_end), status=r.status, weather=r.weather_snapshot)


# ---------------------------------------------------------------- connection

@router.get("/calendar/status", response_model=CalendarStatus)
def calendar_status(user: VerifiedUser, db: DB):
    c = svc.connection(db, user)
    return CalendarStatus(connected=c is not None, status=c.status if c else None,
                          can_read_free_busy=svc.has_scope(c, google.SCOPE_FREEBUSY) or svc.has_scope(c, google.SCOPE_EVENTS),
                          can_add_events=svc.has_scope(c, google.SCOPE_EVENTS))


@router.post("/calendar/connect", response_model=AuthUrl)
def connect(user: VerifiedUser, db: DB):
    """Free. Returns Google's consent URL (free/busy only). The app opens it in a browser session."""
    rate_limit.hit(db, f"calendar-connect:user:{user.id}", limit=10, window_seconds=600)
    return AuthUrl(auth_url=svc.start_authorization(db, user, want_events=False))


@router.get("/calendar/oauth/callback", include_in_schema=False)
def oauth_callback(db: DB, state: str = "", code: str | None = None, error: str | None = None):
    """Google redirects the browser here; we finish the exchange and bounce back into the app."""
    return RedirectResponse(svc.complete_authorization(db, state, code, error), status_code=302)


@router.delete("/calendar", status_code=status.HTTP_204_NO_CONTENT)
def disconnect(user: VerifiedUser, db: DB):
    svc.disconnect(db, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- free time & suggestions

@router.get("/calendar/free-slots", response_model=FreeSlots)
def free_slot_view(user: VerifiedUser, db: DB, day: date | None = Query(default=None, alias="date")):
    d = day or local_today(user)
    slots, used, _ = svc.day_slots(db, user, d)
    return FreeSlots(date=d, timezone=user.timezone, calendar_used=used,
                     slots=[Slot(start=s.start, end=s.end, minutes=int(s.minutes)) for s in slots])


@router.get("/recommendations", response_model=Recommendations)
def get_recommendations(user: VerifiedUser, db: DB, day: date | None = Query(default=None, alias="date")):
    """Water breaks for everyone; weather-aware walk/jog/run ideas for Premium."""
    rate_limit.hit(db, f"recs:user:{user.id}", limit=60, window_seconds=600)
    d = day or local_today(user)
    items, withheld, used = svc.recommendations(db, user, d)
    return Recommendations(date=d, timezone=user.timezone, calendar_used=used, items=[_rec_out(r) for r in items],
                           premium_ideas_available=withheld)


@router.post("/recommendations/{rec_id}/dismiss", response_model=Recommendation)
def dismiss(rec_id: uuid.UUID, user: VerifiedUser, db: DB):
    return _rec_out(svc.dismiss(db, user, rec_id))


@router.post("/recommendations/{rec_id}/schedule", response_model=Recommendation)
def schedule(rec_id: uuid.UUID, user: PremiumUser, db: DB):
    """Premium. Creates a Google Calendar event — only ever on this explicit request."""
    r, _ = svc.schedule(db, user, rec_id)
    return _rec_out(r)


# ---------------------------------------------------------------- preferences

def _prefs_out(p) -> SchedulingPrefs:
    return SchedulingPrefs(working_hours_start=p.working_hours_start, working_hours_end=p.working_hours_end,
                           sleep_start=p.sleep_start or time(22), sleep_end=p.sleep_end or time(6, 30),
                           min_free_slot_minutes=p.min_free_slot_minutes or 15,
                           preferred_activities=list(p.preferred_activities or []),
                           preferred_activity_times=list(p.preferred_activity_times or []))


@router.get("/me/scheduling-preferences", response_model=SchedulingPrefs)
def get_prefs(user: VerifiedUser, db: DB):
    return _prefs_out(svc.preferences(db, user))


@router.patch("/me/scheduling-preferences", response_model=SchedulingPrefs)
def patch_prefs(data: SchedulingPrefsIn, user: VerifiedUser, db: DB):
    p = svc.preferences(db, user)
    changes = data.model_dump(exclude_unset=True)
    if ("working_hours_start" in changes) != ("working_hours_end" in changes):
        raise HTTPException(422, {"code": "invalid_hours", "message": "Set both working-hours times, or clear both."})
    for k, v in changes.items():
        if v is None and k in ("sleep_start", "sleep_end", "min_free_slot_minutes", "preferred_activities",
                               "preferred_activity_times"):
            continue
        setattr(p, k, v)
    if p.sleep_start == p.sleep_end:
        db.rollback()
        raise HTTPException(422, {"code": "invalid_hours", "message": "Bedtime and wake-up time can't be the same."})
    db.commit()
    return _prefs_out(p)
