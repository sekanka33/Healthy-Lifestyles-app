"""Workouts (GPS, manual, health-platform imports), fitness goals and summaries. Premium.

GPS workouts: start (idempotent on client_id) → upload point batches (idempotent on seq) → finish.
The server recomputes distance from accepted points every time, so the client never supplies it.
"""

import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import as_utc, utcnow
from app.models.fitness import FitnessGoal, HealthConnection, Workout, WorkoutPoint
from app.models.user import User, UserPreferences
from app.schemas.fitness import (
    GoalIn,
    GoalProgress,
    HealthImportIn,
    ManualWorkout,
    PointIn,
    RoutePoint,
    WorkoutDetail,
    WorkoutFinish,
    WorkoutOut,
    WorkoutStart,
)
from app.services import geo
from app.services.hydration import local_today

MAX_POINTS_PER_WORKOUT = 20_000
CLOCK_SKEW = timedelta(minutes=5)
MAX_BACKDATE = timedelta(days=30)
MAX_WORKOUT = timedelta(hours=24)


def _err(code: int, key: str, message: str) -> HTTPException:
    return HTTPException(code, {"code": key, "message": message})


def _weight(db: Session, user: User) -> float | None:
    prefs = db.get(UserPreferences, user.id)
    return prefs.body_weight_kg if prefs else None


def _check_start(started_at: datetime) -> datetime:
    now = utcnow()
    at = started_at.astimezone(timezone.utc)
    if at > now + CLOCK_SKEW:
        raise _err(422, "future_timestamp", "The workout can't start in the future.")
    if at < now - MAX_BACKDATE:
        raise _err(422, "too_old", "Workouts can be added at most 30 days back.")
    return at


# ---------------------------------------------------------------- read models

def point_count(db: Session, workout_id: uuid.UUID) -> int:
    return db.execute(select(func.count()).select_from(WorkoutPoint).where(WorkoutPoint.workout_id == workout_id)).scalar_one()


def to_out(db: Session, w: Workout) -> WorkoutOut:
    return WorkoutOut(
        id=w.id, client_id=w.client_id, activity_type=w.activity_type, source=w.source, status=w.status,
        started_at=as_utc(w.started_at), ended_at=as_utc(w.ended_at) if w.ended_at else None,
        active_duration_s=w.active_duration_s, distance_m=round(w.distance_m, 1),
        pace_s_per_km=geo.pace_s_per_km(w.distance_m, w.active_duration_s),
        calories_kcal_estimate=w.calories_kcal_estimate, steps=w.steps, notes=w.notes,
        point_count=point_count(db, w.id),
    )


def to_detail(db: Session, w: Workout) -> WorkoutDetail:
    pts = db.execute(select(WorkoutPoint).where(WorkoutPoint.workout_id == w.id, WorkoutPoint.accepted.is_(True))
                     .order_by(WorkoutPoint.seq)).scalars()
    return WorkoutDetail(**to_out(db, w).model_dump(),
                         route=[RoutePoint(lat=p.lat, lon=p.lon, segment=p.segment) for p in pts])


def get_owned(db: Session, user: User, workout_id: uuid.UUID) -> Workout:
    w = db.get(Workout, workout_id)
    if w is None or w.user_id != user.id:
        raise _err(404, "not_found", "Workout not found.")
    return w


def list_workouts(db: Session, user: User, first: date, last: date) -> list[Workout]:
    start, end = _local_bounds(user, first, last)
    return list(db.execute(
        select(Workout).where(Workout.user_id == user.id, Workout.status == "completed",
                              Workout.started_at >= start, Workout.started_at < end)
        .order_by(Workout.started_at.desc())
    ).scalars())


def _local_bounds(user: User, first: date, last: date) -> tuple[datetime, datetime]:
    tz = ZoneInfo(user.timezone or "UTC")
    start = datetime.combine(first, time.min, tz).astimezone(timezone.utc)
    end = datetime.combine(last + timedelta(days=1), time.min, tz).astimezone(timezone.utc)
    return start, end


# ---------------------------------------------------------------- GPS lifecycle

def _by_client_id(db: Session, user: User, client_id: uuid.UUID) -> Workout | None:
    return db.execute(select(Workout).where(Workout.user_id == user.id, Workout.client_id == client_id)).scalar_one_or_none()


def start(db: Session, user: User, data: WorkoutStart) -> tuple[Workout, bool]:
    existing = _by_client_id(db, user, data.client_id)
    if existing is not None:
        return existing, False
    w = Workout(user_id=user.id, client_id=data.client_id, activity_type=data.activity_type, source="gps",
                status="in_progress", started_at=_check_start(data.started_at))
    db.add(w)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _by_client_id(db, user, data.client_id), False
    return w, True


def _recompute(db: Session, w: Workout) -> None:
    rows = list(db.execute(select(WorkoutPoint).where(WorkoutPoint.workout_id == w.id)).scalars())
    fixes = [geo.Fix(seq=p.seq, segment=p.segment, recorded_at=as_utc(p.recorded_at), lat=p.lat, lon=p.lon,
                     accuracy_m=p.accuracy_m) for p in rows]
    geo.filter_fixes(fixes, w.activity_type)
    accepted = {f.seq: f.accepted for f in fixes}
    for p in rows:
        p.accepted = accepted[p.seq]
    w.distance_m = geo.route_distance_m(fixes)


def add_points(db: Session, w: Workout, points: list[PointIn]) -> int:
    """Stores new fixes (duplicates by seq are ignored) and recomputes distance. Returns how many were new."""
    if w.status != "in_progress":
        raise _err(409, "not_in_progress", "This workout has already ended.")
    existing = set(db.execute(select(WorkoutPoint.seq).where(WorkoutPoint.workout_id == w.id)).scalars())
    if len(existing) + len(points) > MAX_POINTS_PER_WORKOUT:
        raise _err(422, "too_many_points", "This workout has too many location points.")
    started, now = as_utc(w.started_at), utcnow()
    added = 0
    for p in points:
        if p.seq in existing:
            continue
        at = p.recorded_at.astimezone(timezone.utc)
        if at < started - CLOCK_SKEW or at > now + CLOCK_SKEW:
            continue  # outside the workout window: drop silently (stale cache / clock jump)
        db.add(WorkoutPoint(workout_id=w.id, seq=p.seq, segment=p.segment, recorded_at=at, lat=p.lat, lon=p.lon,
                            altitude_m=p.altitude_m, accuracy_m=p.accuracy_m, speed_mps=p.speed_mps))
        existing.add(p.seq)
        added += 1
    db.flush()
    _recompute(db, w)
    try:
        db.commit()
    except IntegrityError:  # concurrent upload of the same batch
        db.rollback()
        return 0
    return added


def finish(db: Session, user: User, w: Workout, data: WorkoutFinish) -> Workout:
    if w.status == "completed":
        return w  # idempotent retry
    if w.status != "in_progress":
        raise _err(409, "not_in_progress", "This workout was discarded.")
    started = as_utc(w.started_at)
    ended = data.ended_at.astimezone(timezone.utc)
    if ended <= started or ended > utcnow() + CLOCK_SKEW or ended - started > MAX_WORKOUT:
        raise _err(422, "invalid_end", "The end time doesn't fit this workout.")
    _recompute(db, w)
    w.ended_at = ended
    w.active_duration_s = min(data.active_duration_s, int((ended - started).total_seconds()))
    w.steps, w.notes, w.status = data.steps, data.notes, "completed"
    w.calories_kcal_estimate = geo.calories_estimate(w.activity_type, w.active_duration_s, _weight(db, user))
    db.commit()
    return w


def discard(db: Session, w: Workout) -> Workout:
    if w.status == "in_progress":
        w.status = "discarded"
        db.commit()
    return w


def add_manual(db: Session, user: User, data: ManualWorkout) -> tuple[Workout, bool]:
    existing = _by_client_id(db, user, data.client_id)
    if existing is not None:
        return existing, False
    started = _check_start(data.started_at)
    ended = started + timedelta(seconds=data.active_duration_s)
    if ended > utcnow() + CLOCK_SKEW:
        raise _err(422, "future_timestamp", "That workout would end in the future.")
    w = Workout(user_id=user.id, client_id=data.client_id, activity_type=data.activity_type, source="manual",
                status="completed", started_at=started, ended_at=ended, active_duration_s=data.active_duration_s,
                distance_m=data.distance_m, steps=data.steps, notes=data.notes,
                calories_kcal_estimate=geo.calories_estimate(data.activity_type, data.active_duration_s, _weight(db, user)))
    db.add(w)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _by_client_id(db, user, data.client_id), False
    return w, True


def delete_workout(db: Session, w: Workout) -> None:
    db.delete(w)  # points cascade: the route is gone too
    db.commit()


# ---------------------------------------------------------------- health platforms

def list_connections(db: Session, user: User) -> list[HealthConnection]:
    return list(db.execute(select(HealthConnection).where(HealthConnection.user_id == user.id)).scalars())


def upsert_connection(db: Session, user: User, provider: str, data_types: list[str]) -> HealthConnection:
    c = db.execute(select(HealthConnection).where(HealthConnection.user_id == user.id,
                                                  HealthConnection.provider == provider)).scalar_one_or_none()
    if c is None:
        c = HealthConnection(user_id=user.id, provider=provider)
        db.add(c)
    c.granted_data_types = sorted(set(data_types))
    c.connected_at, c.revoked_at = utcnow(), None
    db.commit()
    return c


def revoke_connection(db: Session, user: User, provider: str, delete_imported: bool) -> None:
    c = db.execute(select(HealthConnection).where(HealthConnection.user_id == user.id,
                                                  HealthConnection.provider == provider)).scalar_one_or_none()
    if c is not None:
        c.revoked_at = utcnow()
    if delete_imported:
        for w in db.execute(select(Workout).where(Workout.user_id == user.id, Workout.source == provider)).scalars():
            db.delete(w)
    db.commit()


def import_records(db: Session, user: User, data: HealthImportIn) -> tuple[int, int, int]:
    c = db.execute(select(HealthConnection).where(HealthConnection.user_id == user.id,
                                                  HealthConnection.provider == data.provider)).scalar_one_or_none()
    if c is None or c.revoked_at is not None:
        raise _err(409, "not_connected", "Connect this health app first.")
    weight = _weight(db, user)
    imported = updated = skipped = 0
    now = utcnow()
    for r in data.records:
        started, ended = r.started_at.astimezone(timezone.utc), r.ended_at.astimezone(timezone.utc)
        if ended > now + CLOCK_SKEW or ended - started > MAX_WORKOUT or started < now - timedelta(days=365):
            skipped += 1
            continue
        w = db.execute(select(Workout).where(Workout.user_id == user.id, Workout.source == data.provider,
                                             Workout.external_id == r.external_id)).scalar_one_or_none()
        seconds = int((ended - started).total_seconds())
        if w is None:
            w = Workout(user_id=user.id, client_id=uuid.uuid5(uuid.NAMESPACE_URL, f"{data.provider}:{r.external_id}"),
                        source=data.provider, external_id=r.external_id, status="completed")
            db.add(w)
            imported += 1
        else:
            updated += 1
        w.activity_type, w.started_at, w.ended_at = r.activity_type, started, ended
        w.active_duration_s, w.distance_m, w.steps = seconds, r.distance_m or 0.0, r.steps
        w.calories_kcal_estimate = geo.calories_estimate(r.activity_type, seconds, weight)
    c.last_synced_at = now
    db.commit()
    return imported, updated, skipped


# ---------------------------------------------------------------- goals & summary

def period_bounds(user: User, period: str) -> tuple[date, date]:
    today = local_today(user)
    if period == "weekly":
        start = today - timedelta(days=today.isoweekday() - 1)  # Monday
        return start, start + timedelta(days=6)
    start = today.replace(day=1)
    nxt = (start + timedelta(days=32)).replace(day=1)
    return start, nxt - timedelta(days=1)


def _metric(workouts: list[Workout], metric: str, activity: str | None) -> float:
    ws = [w for w in workouts if activity is None or w.activity_type == activity]
    if metric == "distance_km":
        return round(sum(w.distance_m for w in ws) / 1000, 2)
    if metric == "workout_count":
        return float(len(ws))
    return round(sum(w.active_duration_s for w in ws) / 60, 1)


def list_goals(db: Session, user: User) -> list[FitnessGoal]:
    return list(db.execute(select(FitnessGoal).where(FitnessGoal.user_id == user.id, FitnessGoal.active.is_(True))
                           .order_by(FitnessGoal.created_at)).scalars())


def goal_progress(db: Session, user: User, g: FitnessGoal) -> GoalProgress:
    first, last = period_bounds(user, g.period)
    value = _metric(list_workouts(db, user, first, last), g.metric, g.activity_type)
    return GoalProgress(id=g.id, metric=g.metric, period=g.period, target_value=g.target_value,
                        activity_type=g.activity_type, current_value=value,
                        progress=round(value / g.target_value, 4), period_start=first, period_end=last)


def add_goal(db: Session, user: User, data: GoalIn) -> FitnessGoal:
    if len(list_goals(db, user)) >= 10:
        raise _err(422, "limit_reached", "You can have up to 10 active goals.")
    g = FitnessGoal(user_id=user.id, **data.model_dump())
    db.add(g)
    db.commit()
    return g


def remove_goal(db: Session, user: User, goal_id: uuid.UUID) -> None:
    g = db.get(FitnessGoal, goal_id)
    if g is None or g.user_id != user.id:
        raise _err(404, "not_found", "Goal not found.")
    g.active = False
    db.commit()
