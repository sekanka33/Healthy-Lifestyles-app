"""Google Calendar connection, free-slot view and recommendations.

Security:
- OAuth `state` is random, single-use, expires in 10 minutes and is stored only as a SHA-256 hash.
- PKCE (S256) verifier and Google tokens are Fernet-encrypted at rest; tokens are never logged or
  returned to the app.
- Only free/busy times are read by default; event details are never fetched.
"""

import logging
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core import crypto, security
from app.core.config import get_settings
from app.db.base import as_utc, utcnow
from app.models.integrations import ActivityRecommendation, CalendarEventRecord, OAuthConnection, OAuthState
from app.models.user import User, UserPreferences
from app.services import google_calendar as google
from app.services import weather as weather_svc
from app.services.entitlements import is_premium
from app.services.scheduling import Interval, free_slots, local_window, recommend

logger = logging.getLogger("app.calendar")
STATE_TTL = timedelta(minutes=10)


def _err(code: int, key: str, message: str, **extra) -> HTTPException:
    return HTTPException(code, {"code": key, "message": message, **extra})


def _not_configured() -> HTTPException:
    return _err(503, "calendar_not_configured", "Google Calendar isn't available right now.")


def connection(db: Session, user: User) -> OAuthConnection | None:
    return db.execute(select(OAuthConnection).where(OAuthConnection.user_id == user.id,
                                                    OAuthConnection.provider == "google")).scalar_one_or_none()


def has_scope(c: OAuthConnection | None, scope: str) -> bool:
    return bool(c and c.status == "active" and scope in (c.scopes or "").split())


# ---------------------------------------------------------------- OAuth

def start_authorization(db: Session, user: User, *, want_events: bool) -> str:
    try:
        client = google.get_client()
        verifier, challenge = google.new_pkce()
        enc_verifier = crypto.encrypt(verifier)
    except (google.GoogleNotConfigured, crypto.EncryptionNotConfigured):
        raise _not_configured() from None
    scopes = [google.SCOPE_FREEBUSY] + ([google.SCOPE_EVENTS] if want_events else [])
    state = security.new_opaque_token()
    # Clean up this user's abandoned attempts.
    db.execute(delete(OAuthState).where(OAuthState.user_id == user.id, OAuthState.consumed_at.is_(None)))
    db.add(OAuthState(user_id=user.id, state_hash=security.sha256_hex(state), code_verifier_enc=enc_verifier,
                      requested_scopes=" ".join(scopes), expires_at=utcnow() + STATE_TTL))
    db.commit()
    return client.authorization_url(state=state, code_challenge=challenge, scopes=scopes)


def complete_authorization(db: Session, state: str, code: str | None, error: str | None) -> str:
    """Returns the app deep-link to redirect to: ...calendar-connected?status=ok|denied|error."""
    link = get_settings().app_deep_link_base
    base = (link if link.endswith("/") else link + "/") + "calendar-connected"  # keep "scheme://" intact
    row = db.execute(select(OAuthState).where(OAuthState.state_hash == security.sha256_hex(state or ""))
                     ).scalar_one_or_none()
    if row is None or row.consumed_at is not None or as_utc(row.expires_at) <= utcnow():
        return f"{base}?status=error"
    row.consumed_at = utcnow()  # single use, even if the rest fails
    db.commit()
    if error or not code:
        return f"{base}?status=denied"
    try:
        verifier = crypto.decrypt(row.code_verifier_enc)
        tokens = google.get_client().exchange_code(code, verifier or "")
    except (google.GoogleError, google.GoogleNotConfigured, crypto.EncryptionNotConfigured) as exc:
        logger.warning("Google code exchange failed: %s", type(exc).__name__)
        return f"{base}?status=error"
    granted = tokens.get("scope", "")
    if google.SCOPE_FREEBUSY not in granted.split() and google.SCOPE_EVENTS not in granted.split():
        return f"{base}?status=denied"  # user unticked the calendar permission
    c = db.execute(select(OAuthConnection).where(OAuthConnection.user_id == row.user_id,
                                                 OAuthConnection.provider == "google")).scalar_one_or_none()
    if c is None:
        c = OAuthConnection(user_id=row.user_id, provider="google", scopes="")
        db.add(c)
    c.scopes = " ".join(sorted(set((c.scopes or "").split()) | set(granted.split())))
    c.access_token_enc = crypto.encrypt(tokens["access_token"])
    c.access_token_expires_at = utcnow() + timedelta(seconds=int(tokens.get("expires_in", 3600)) - 60)
    if tokens.get("refresh_token"):
        c.refresh_token_enc = crypto.encrypt(tokens["refresh_token"])
    c.status, c.last_error = "active", None
    db.commit()
    return f"{base}?status=ok"


def _access_token(db: Session, c: OAuthConnection) -> str:
    if c.access_token_enc and c.access_token_expires_at and as_utc(c.access_token_expires_at) > utcnow():
        token = crypto.decrypt(c.access_token_enc)
        if token:
            return token
    refresh = crypto.decrypt(c.refresh_token_enc) if c.refresh_token_enc else None
    if not refresh:
        c.status = "error"
        db.commit()
        raise _err(409, "calendar_reconnect", "Please reconnect Google Calendar.")
    try:
        tokens = google.get_client().refresh(refresh)
    except google.GoogleError as exc:
        if exc.auth_revoked:
            c.status, c.last_error = "revoked", "access revoked"
            db.commit()
            raise _err(409, "calendar_reconnect", "Google Calendar access was removed. Please reconnect.") from None
        raise _err(503, "calendar_unavailable", "Google Calendar is unavailable right now.") from None
    c.access_token_enc = crypto.encrypt(tokens["access_token"])
    c.access_token_expires_at = utcnow() + timedelta(seconds=int(tokens.get("expires_in", 3600)) - 60)
    db.commit()
    return tokens["access_token"]


def disconnect(db: Session, user: User) -> None:
    c = connection(db, user)
    if c is None:
        return
    token = crypto.decrypt(c.refresh_token_enc) if c.refresh_token_enc else None
    if token:
        try:
            google.get_client().revoke(token)
        except google.GoogleNotConfigured:
            pass
    db.delete(c)
    db.commit()


# ---------------------------------------------------------------- free time

def preferences(db: Session, user: User) -> UserPreferences:
    p = db.get(UserPreferences, user.id)
    if p is None:
        p = UserPreferences(user_id=user.id)
        db.add(p)
        db.commit()
    return p


def _busy(db: Session, user: User, start: datetime, end: datetime) -> tuple[list[Interval], bool]:
    """(busy intervals, calendar_used). Without a working connection the day is treated as open."""
    c = connection(db, user)
    if not has_scope(c, google.SCOPE_FREEBUSY) and not has_scope(c, google.SCOPE_EVENTS):
        return [], False
    try:
        token = _access_token(db, c)
        raw = google.get_client().free_busy(token, start, end, list(c.selected_calendar_ids or ["primary"]))
    except google.GoogleError as exc:
        if exc.auth_revoked:
            c.status = "revoked"
            db.commit()
            raise _err(409, "calendar_reconnect", "Google Calendar access was removed. Please reconnect.") from None
        raise _err(503, "calendar_unavailable", "Google Calendar is unavailable right now.") from None
    return [Interval(datetime.fromisoformat(s.replace("Z", "+00:00")), datetime.fromisoformat(e.replace("Z", "+00:00")))
            for s, e in raw], True


def day_slots(db: Session, user: User, day: date) -> tuple[list[Interval], bool, UserPreferences]:
    p = preferences(db, user)
    tz = ZoneInfo(user.timezone)
    awake = local_window(day, tz, p.sleep_end or time(6, 30), p.sleep_start or time(22))
    busy, used = _busy(db, user, awake.start, awake.end)
    slots = free_slots(day, user.timezone, busy, wake=p.sleep_end or time(6, 30), sleep=p.sleep_start or time(22),
                       min_minutes=p.min_free_slot_minutes or 15, now=utcnow())
    return slots, used, p


# ---------------------------------------------------------------- recommendations

def _forecast_steps(db: Session, p: UserPreferences) -> list[dict] | None:
    if p.weather_lat is None or p.weather_lon is None:
        return None
    try:
        return weather_svc.forecast(db, p.weather_lat, p.weather_lon, hours=48)["steps"]
    except HTTPException:
        return None  # weather down / not configured: still recommend, just without weather


def recommendations(db: Session, user: User, day: date) -> tuple[list[ActivityRecommendation], int, bool]:
    premium = is_premium(db, user)
    slots, used, p = day_slots(db, user, day)
    tz = ZoneInfo(user.timezone)
    working = None
    if p.working_hours_start and p.working_hours_end:
        working = local_window(day, tz, p.working_hours_start, p.working_hours_end)
    suggestions, withheld = recommend(
        slots, tz_name=user.timezone, premium=premium, forecast=_forecast_steps(db, p) if premium else None,
        preferred_activities=list(p.preferred_activities or []), preferred_times=list(p.preferred_activity_times or []),
        working=working,
    )
    # Replace today's unanswered suggestions; keep anything the user accepted or scheduled.
    day_window = local_window(day, tz, time(0), time(0))
    db.execute(delete(ActivityRecommendation).where(
        ActivityRecommendation.user_id == user.id, ActivityRecommendation.status == "suggested",
        ActivityRecommendation.suggested_start >= day_window.start, ActivityRecommendation.suggested_start < day_window.end))
    kept = list(db.execute(select(ActivityRecommendation).where(
        ActivityRecommendation.user_id == user.id, ActivityRecommendation.status.in_(("accepted", "scheduled", "dismissed")),
        ActivityRecommendation.suggested_start >= day_window.start, ActivityRecommendation.suggested_start < day_window.end,
    )).scalars())
    taken = {(r.kind, as_utc(r.suggested_start)) for r in kept}
    rows = []
    for s in suggestions:
        if (s.kind, s.start) in taken:
            continue
        r = ActivityRecommendation(user_id=user.id, kind=s.kind, title=s.title, reason=s.reason,
                                   slot_start=s.slot.start, slot_end=s.slot.end, suggested_start=s.start,
                                   suggested_end=s.end, weather_snapshot=_jsonable(s.weather))
        db.add(r)
        rows.append(r)
    db.commit()
    visible = [r for r in kept if r.status != "dismissed"] + rows
    return sorted(visible, key=lambda r: as_utc(r.suggested_start)), withheld, used


def _jsonable(w: dict | None) -> dict | None:
    if not w:
        return None
    return {"temp_c": w.get("temp_c"), "condition": w.get("condition"), "outdoor": w.get("outdoor")}


def _owned(db: Session, user: User, rec_id: uuid.UUID) -> ActivityRecommendation:
    r = db.get(ActivityRecommendation, rec_id)
    if r is None or r.user_id != user.id:
        raise _err(404, "not_found", "Suggestion not found.")
    return r


def dismiss(db: Session, user: User, rec_id: uuid.UUID) -> ActivityRecommendation:
    r = _owned(db, user, rec_id)
    if r.status == "suggested":
        r.status = "dismissed"
        db.commit()
    return r


def schedule(db: Session, user: User, rec_id: uuid.UUID) -> tuple[ActivityRecommendation, CalendarEventRecord]:
    """Premium: adds the suggestion to Google Calendar, only after the user explicitly asks."""
    r = _owned(db, user, rec_id)
    existing = db.execute(select(CalendarEventRecord).where(CalendarEventRecord.recommendation_id == r.id)).scalar_one_or_none()
    if existing is not None:
        return r, existing  # idempotent: double taps never create two events
    if r.status == "dismissed":
        raise _err(409, "dismissed", "That suggestion was dismissed.")
    if as_utc(r.suggested_end) <= utcnow():
        raise _err(409, "in_the_past", "That time has already passed.")
    c = connection(db, user)
    if not has_scope(c, google.SCOPE_EVENTS):
        # Incremental authorisation: ask for event access now, not at first connect.
        raise _err(409, "needs_calendar_permission", "Allow the app to add events to your Google Calendar.",
                   auth_url=start_authorization(db, user, want_events=True))
    token = _access_token(db, c)
    tz = user.timezone
    try:
        event = google.get_client().create_event(
            token, calendar_id="primary", summary=r.title,
            description=f"{r.reason}\n\nAdded by {get_settings().app_name}.",
            start=as_utc(r.suggested_start).astimezone(ZoneInfo(tz)), end=as_utc(r.suggested_end).astimezone(ZoneInfo(tz)), tz=tz)
    except google.GoogleError as exc:
        if exc.auth_revoked:
            raise _err(409, "calendar_reconnect", "Please reconnect Google Calendar.") from None
        raise _err(503, "calendar_unavailable", "Couldn't add it to Google Calendar. Try again.") from None
    rec = CalendarEventRecord(user_id=user.id, recommendation_id=r.id, calendar_id="primary",
                              google_event_id=str(event.get("id")), title=r.title,
                              start_at=r.suggested_start, end_at=r.suggested_end)
    r.status = "scheduled"
    db.add(rec)
    db.commit()
    return r, rec
