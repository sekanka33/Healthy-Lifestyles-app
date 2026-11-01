from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.api.deps import DB, AnyUser
from app.db.base import as_utc
from app.models.user import NotificationPreferences, User, UserPreferences
from app.schemas.user import (
    FitnessProfileOut,
    FitnessProfileUpdate,
    NotificationPrefsOut,
    NotificationPrefsUpdate,
    UserOut,
    UserUpdate,
)
from app.services.entitlements import plan

router = APIRouter(prefix="/me", tags=["profile"])


def user_out(db: Session, user: User) -> UserOut:
    return UserOut(
        id=user.id, email=user.email, first_name=user.first_name, last_name=user.last_name,
        email_verified=user.email_verified_at is not None, timezone=user.timezone, locale=user.locale,
        units=user.units, plan=plan(db, user), created_at=as_utc(user.created_at),
    )


@router.get("", response_model=UserOut)
def get_me(user: AnyUser, db: DB):
    return user_out(db, user)


@router.patch("", response_model=UserOut)
def update_me(data: UserUpdate, user: AnyUser, db: DB):
    changes = data.model_dump(exclude_unset=True)
    if changes.get("first_name") is None:
        changes.pop("first_name", None)  # required field: ignore explicit null
    for field, value in changes.items():
        setattr(user, field, value.strip() if isinstance(value, str) else value)
    if "last_name" in changes and not user.last_name:
        user.last_name = None
    db.commit()
    return user_out(db, user)


def _notification_prefs(db: Session, user: User) -> NotificationPreferences:
    prefs = db.get(NotificationPreferences, user.id)
    if prefs is None:
        prefs = NotificationPreferences(user_id=user.id)
        db.add(prefs)
        db.commit()
    return prefs


@router.get("/notification-preferences", response_model=NotificationPrefsOut)
def get_notification_prefs(user: AnyUser, db: DB):
    return _notification_prefs(db, user)


@router.patch("/notification-preferences", response_model=NotificationPrefsOut)
def update_notification_prefs(data: NotificationPrefsUpdate, user: AnyUser, db: DB):
    prefs = _notification_prefs(db, user)
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is None and field not in ("quiet_hours_start", "quiet_hours_end"):
            continue
        setattr(prefs, field, value)
    db.commit()
    return prefs


def _preferences(db: Session, user: User) -> UserPreferences:
    prefs = db.get(UserPreferences, user.id)
    if prefs is None:
        prefs = UserPreferences(user_id=user.id)
        db.add(prefs)
        db.commit()
    return prefs


@router.get("/fitness-profile", response_model=FitnessProfileOut)
def get_fitness_profile(user: AnyUser, db: DB):
    return _preferences(db, user)


@router.put("/fitness-profile", response_model=FitnessProfileOut)
def put_fitness_profile(data: FitnessProfileUpdate, user: AnyUser, db: DB):
    """Body weight is optional and only used to estimate calories. Send null to remove it."""
    prefs = _preferences(db, user)
    prefs.body_weight_kg = data.body_weight_kg
    db.commit()
    return prefs
