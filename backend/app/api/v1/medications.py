import uuid
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from pydantic import AwareDatetime

from app.api.deps import DB, PremiumUser, VerifiedUser
from app.db.base import as_utc
from app.schemas.medication import (
    AdherenceOut,
    DoseIn,
    DoseOut,
    MedicationCreate,
    MedicationOut,
    MedicationUpdate,
    ScheduledDose,
)
from app.services import medication as svc
from app.services.hydration import local_today

router = APIRouter(prefix="/medications", tags=["medications"])

# Premium is required to create, schedule and log. Listing and deleting stay open to any verified user,
# so someone whose subscription lapsed can still see and erase their own health data.


@router.get("", response_model=list[MedicationOut])
def list_medications(user: VerifiedUser, db: DB, include_discontinued: bool = True):
    return [svc.to_out(m) for m in svc.list_medications(db, user, include_discontinued)]


@router.post("", response_model=MedicationOut, status_code=status.HTTP_201_CREATED)
def create(data: MedicationCreate, user: PremiumUser, db: DB):
    return svc.to_out(svc.create(db, user, data))


@router.get("/schedule", response_model=list[ScheduledDose])
def schedule(
    user: PremiumUser,
    db: DB,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
):
    """Every dose between two local dates (default: today) with its recorded status."""
    first = from_ or local_today(user)
    return svc.scheduled_doses(db, user, first, to or first)


@router.get("/adherence", response_model=AdherenceOut)
def adherence(
    user: PremiumUser,
    db: DB,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
):
    """Per-medication summary for a date range (default: the last 7 days)."""
    last = to or local_today(user)
    first = from_ or last - timedelta(days=6)
    return AdherenceOut(from_date=first, to_date=last, timezone=user.timezone,
                        medications=svc.adherence(db, user, first, last))


@router.get("/{med_id}", response_model=MedicationOut)
def get_one(med_id: uuid.UUID, user: PremiumUser, db: DB):
    return svc.to_out(svc.get_owned(db, user, med_id))


@router.patch("/{med_id}", response_model=MedicationOut)
def update(med_id: uuid.UUID, data: MedicationUpdate, user: PremiumUser, db: DB):
    return svc.to_out(svc.update(db, user, svc.get_owned(db, user, med_id), data))


@router.post("/{med_id}/discontinue", response_model=MedicationOut)
def discontinue(med_id: uuid.UUID, user: PremiumUser, db: DB):
    return svc.to_out(svc.discontinue(db, svc.get_owned(db, user, med_id)))


@router.post("/{med_id}/resume", response_model=MedicationOut)
def resume(med_id: uuid.UUID, user: PremiumUser, db: DB):
    return svc.to_out(svc.resume(db, user, svc.get_owned(db, user, med_id)))


@router.delete("/{med_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(med_id: uuid.UUID, user: VerifiedUser, db: DB):
    svc.delete_medication(db, svc.get_owned(db, user, med_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{med_id}/doses", response_model=DoseOut)
def record_dose(med_id: uuid.UUID, data: DoseIn, user: PremiumUser, db: DB, response: Response):
    m = svc.get_owned(db, user, med_id)
    dose, created = svc.record_dose(db, user, m, data.scheduled_for, data.status, data.note)
    if created:
        response.status_code = status.HTTP_201_CREATED
    return DoseOut(medication_id=m.id, scheduled_for=as_utc(dose.scheduled_for), status=dose.status,
                   recorded_at=as_utc(dose.recorded_at), note=dose.note)


@router.delete("/{med_id}/doses", status_code=status.HTTP_204_NO_CONTENT)
def clear_dose(med_id: uuid.UUID, scheduled_for: AwareDatetime, user: PremiumUser, db: DB):
    """Undo a recorded outcome (the dose goes back to upcoming/unrecorded)."""
    svc.clear_dose(db, svc.get_owned(db, user, med_id), scheduled_for)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
