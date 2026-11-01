import uuid
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DB, VerifiedUser
from app.schemas.hydration import EntryIn, EntryOut, GoalIn, GoalOut, HistoryOut, TodayOut
from app.services import hydration as svc

router = APIRouter(prefix="/hydration", tags=["hydration"])


@router.post("/entries", response_model=EntryOut, status_code=status.HTTP_201_CREATED,
             responses={200: {"description": "Already recorded (idempotent replay)", "model": EntryOut}})
def add_entry(data: EntryIn, user: VerifiedUser, db: DB, response: Response):
    entry, created = svc.add_entry(db, user, data)
    if not created:
        response.status_code = status.HTTP_200_OK
    return svc.to_out(entry)


@router.delete("/entries/{client_id}", response_model=EntryOut)
def delete_entry(client_id: uuid.UUID, user: VerifiedUser, db: DB):
    return svc.to_out(svc.delete_entry(db, user, client_id))


@router.get("/today", response_model=TodayOut)
def today(user: VerifiedUser, db: DB):
    return _day(db, user, svc.local_today(user))


@router.get("/days/{day}", response_model=TodayOut)
def day(day: date, user: VerifiedUser, db: DB):
    return _day(db, user, day)


def _day(db, user, day: date) -> TodayOut:
    summary, entries = svc.day_detail(db, user, day)
    return TodayOut(**summary.model_dump(), timezone=user.timezone, entries=[svc.to_out(e) for e in entries])


@router.get("/history", response_model=HistoryOut)
def history(
    user: VerifiedUser,
    db: DB,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
):
    """Daily totals for an inclusive local-date range (default: the last 7 days)."""
    end = to or svc.local_today(user)
    start = from_ or end - timedelta(days=6)
    return HistoryOut(timezone=user.timezone, days=svc.history(db, user, start, end))


@router.get("/goal", response_model=GoalOut)
def get_goal(user: VerifiedUser, db: DB):
    row = svc.current_goal(db, user)
    if row is None:
        return GoalOut(daily_goal_ml=svc.DEFAULT_GOAL_ML, effective_from=None)
    return GoalOut(daily_goal_ml=row.daily_goal_ml, effective_from=row.effective_from)


@router.put("/goal", response_model=GoalOut)
def put_goal(data: GoalIn, user: VerifiedUser, db: DB):
    row = svc.set_goal(db, user, data.daily_goal_ml)
    return GoalOut(daily_goal_ml=row.daily_goal_ml, effective_from=row.effective_from)
