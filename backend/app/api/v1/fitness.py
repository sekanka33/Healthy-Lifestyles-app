import uuid
from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DB, PremiumUser, VerifiedUser
from app.db.base import as_utc
from app.schemas.fitness import (
    GoalIn,
    GoalProgress,
    HealthConnectionIn,
    HealthConnectionOut,
    HealthImportIn,
    HealthImportOut,
    HealthProvider,
    ManualWorkout,
    PointsIn,
    SummaryOut,
    WorkoutDetail,
    WorkoutFinish,
    WorkoutOut,
    WorkoutStart,
)
from app.services import fitness as svc
from app.services.hydration import local_today

router = APIRouter(tags=["fitness"])

# Same policy as medication: creating and syncing is Premium; viewing your list and deleting stay open
# to any verified user so lapsed subscribers keep control of their (location) data.


@router.get("/workouts", response_model=list[WorkoutOut])
def list_workouts(
    user: VerifiedUser, db: DB,
    from_: Annotated[date | None, Query(alias="from")] = None, to: date | None = None,
):
    last = to or local_today(user)
    first = from_ or last - timedelta(days=29)
    if last < first or (last - first).days > 366:
        return []
    return [svc.to_out(db, w) for w in svc.list_workouts(db, user, first, last)]


@router.post("/workouts", response_model=WorkoutOut, status_code=status.HTTP_201_CREATED)
def start_workout(data: WorkoutStart, user: PremiumUser, db: DB, response: Response):
    w, created = svc.start(db, user, data)
    if not created:
        response.status_code = status.HTTP_200_OK
    return svc.to_out(db, w)


@router.post("/workouts/manual", response_model=WorkoutOut, status_code=status.HTTP_201_CREATED)
def manual_workout(data: ManualWorkout, user: PremiumUser, db: DB, response: Response):
    w, created = svc.add_manual(db, user, data)
    if not created:
        response.status_code = status.HTTP_200_OK
    return svc.to_out(db, w)


@router.get("/workouts/{workout_id}", response_model=WorkoutDetail)
def get_workout(workout_id: uuid.UUID, user: VerifiedUser, db: DB):
    return svc.to_detail(db, svc.get_owned(db, user, workout_id))


@router.post("/workouts/{workout_id}/points")
def add_points(workout_id: uuid.UUID, data: PointsIn, user: PremiumUser, db: DB):
    w = svc.get_owned(db, user, workout_id)
    added = svc.add_points(db, w, data.points)
    return {"added": added, "distance_m": round(w.distance_m, 1)}


@router.post("/workouts/{workout_id}/finish", response_model=WorkoutOut)
def finish_workout(workout_id: uuid.UUID, data: WorkoutFinish, user: PremiumUser, db: DB):
    return svc.to_out(db, svc.finish(db, user, svc.get_owned(db, user, workout_id), data))


@router.post("/workouts/{workout_id}/discard", response_model=WorkoutOut)
def discard_workout(workout_id: uuid.UUID, user: PremiumUser, db: DB):
    return svc.to_out(db, svc.discard(db, svc.get_owned(db, user, workout_id)))


@router.delete("/workouts/{workout_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workout(workout_id: uuid.UUID, user: VerifiedUser, db: DB):
    svc.delete_workout(db, svc.get_owned(db, user, workout_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- health platforms

@router.get("/health/connections", response_model=list[HealthConnectionOut])
def connections(user: VerifiedUser, db: DB):
    rows = svc.list_connections(db, user)
    return [HealthConnectionOut(provider=c.provider, granted_data_types=c.granted_data_types,
                                connected_at=as_utc(c.connected_at),
                                last_synced_at=as_utc(c.last_synced_at) if c.last_synced_at else None,
                                active=c.revoked_at is None) for c in rows]


@router.put("/health/connections/{provider}", response_model=HealthConnectionOut)
def connect(provider: HealthProvider, data: HealthConnectionIn, user: PremiumUser, db: DB):
    c = svc.upsert_connection(db, user, provider, data.granted_data_types)
    return HealthConnectionOut(provider=c.provider, granted_data_types=c.granted_data_types,
                               connected_at=as_utc(c.connected_at),
                               last_synced_at=as_utc(c.last_synced_at) if c.last_synced_at else None, active=True)


@router.delete("/health/connections/{provider}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect(provider: HealthProvider, user: VerifiedUser, db: DB, delete_imported: bool = False):
    svc.revoke_connection(db, user, provider, delete_imported)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/health/import", response_model=HealthImportOut)
def health_import(data: HealthImportIn, user: PremiumUser, db: DB):
    imported, updated, skipped = svc.import_records(db, user, data)
    return HealthImportOut(imported=imported, updated=updated, skipped=skipped)


# ---------------------------------------------------------------- goals & summary

@router.get("/fitness/goals", response_model=list[GoalProgress])
def goals(user: PremiumUser, db: DB):
    return [svc.goal_progress(db, user, g) for g in svc.list_goals(db, user)]


@router.post("/fitness/goals", response_model=GoalProgress, status_code=status.HTTP_201_CREATED)
def add_goal(data: GoalIn, user: PremiumUser, db: DB):
    return svc.goal_progress(db, user, svc.add_goal(db, user, data))


@router.delete("/fitness/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_goal(goal_id: uuid.UUID, user: PremiumUser, db: DB):
    svc.remove_goal(db, user, goal_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/fitness/summary", response_model=SummaryOut)
def summary(user: PremiumUser, db: DB, period: Literal["weekly", "monthly"] = "weekly"):
    first, last = svc.period_bounds(user, period)
    ws = svc.list_workouts(db, user, first, last)
    cals = [w.calories_kcal_estimate for w in ws if w.calories_kcal_estimate is not None]
    return SummaryOut(
        period=period, period_start=first, period_end=last, timezone=user.timezone, workouts=len(ws),
        distance_km=round(sum(w.distance_m for w in ws) / 1000, 2),
        active_minutes=round(sum(w.active_duration_s for w in ws) / 60, 1),
        calories_kcal_estimate=round(sum(cals), 1) if cals else None,
        goals=[svc.goal_progress(db, user, g) for g in svc.list_goals(db, user) if g.period == period],
    )
