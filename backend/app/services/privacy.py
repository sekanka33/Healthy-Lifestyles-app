"""Data export and account deletion.

Export: everything we hold about the user as JSON — never password hashes, tokens or codes.
Deletion: revokes Google access, then deletes the user row; every table cascades (ON DELETE CASCADE)
or is detached (email log rows keep only an anonymised status). Store subscriptions can only be
cancelled by the user in their App Store / Google Play account, so the app reminds them.
"""

import json
import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.models import (
    ActivityRecommendation, CalendarEventRecord, EmailPreferences, FitnessGoal, HealthConnection, HydrationEntry,
    HydrationGoal, Medication, MedicationDose, NotificationPreferences, OAuthConnection, PaymentTransaction,
    SubscriptionEntitlement, User, UserPreferences, Workout, WorkoutPoint,
)
from app.models.billing import EmailMessage

SECRET_COLUMNS = {"password_hash", "refresh_token_enc", "access_token_enc", "token_hash", "code_hash",
                  "code_verifier_enc", "state_hash"}


def _plain(obj) -> dict:
    out = {}
    for col in inspect(obj).mapper.column_attrs:
        if col.key in SECRET_COLUMNS:
            continue
        v = getattr(obj, col.key)
        if isinstance(v, (datetime, date, time)):
            v = v.isoformat()
        elif isinstance(v, Decimal):
            v = str(v)
        elif isinstance(v, uuid.UUID):
            v = str(v)
        out[col.key] = v
    return out


def export(db: Session, user: User) -> dict:
    uid = user.id

    def rows(model, *where):
        return [_plain(r) for r in db.execute(select(model).where(*where)).scalars()]

    workouts = list(db.execute(select(Workout).where(Workout.user_id == uid)).scalars())
    meds = list(db.execute(select(Medication).where(Medication.user_id == uid)).scalars())
    data = {
        "exported_at": datetime.now().astimezone().isoformat(),
        "format": "lifepulse-export/1",
        "account": _plain(user),
        "preferences": rows(UserPreferences, UserPreferences.user_id == uid),
        "notification_preferences": rows(NotificationPreferences, NotificationPreferences.user_id == uid),
        "email_preferences": rows(EmailPreferences, EmailPreferences.user_id == uid),
        "hydration_goals": rows(HydrationGoal, HydrationGoal.user_id == uid),
        "hydration_entries": rows(HydrationEntry, HydrationEntry.user_id == uid),
        "medications": [_plain(m) for m in meds],
        "medication_doses": rows(MedicationDose, MedicationDose.user_id == uid),
        "workouts": [{**_plain(w), "route": [_plain(p) for p in db.execute(
            select(WorkoutPoint).where(WorkoutPoint.workout_id == w.id).order_by(WorkoutPoint.seq)).scalars()]}
            for w in workouts],
        "fitness_goals": rows(FitnessGoal, FitnessGoal.user_id == uid),
        "health_connections": rows(HealthConnection, HealthConnection.user_id == uid),
        "calendar_connection": [{k: v for k, v in _plain(c).items()} for c in
                                db.execute(select(OAuthConnection).where(OAuthConnection.user_id == uid)).scalars()],
        "calendar_events_created": rows(CalendarEventRecord, CalendarEventRecord.user_id == uid),
        "recommendations": rows(ActivityRecommendation, ActivityRecommendation.user_id == uid),
        "subscription": rows(SubscriptionEntitlement, SubscriptionEntitlement.user_id == uid),
        "payments": rows(PaymentTransaction, PaymentTransaction.user_id == uid),
        "emails_sent": [{"template": e.template, "status": e.status, "created_at": e.created_at.isoformat()}
                        for e in db.execute(select(EmailMessage).where(EmailMessage.user_id == uid)).scalars()],
    }
    return data


def export_bytes(db: Session, user: User) -> bytes:
    return json.dumps(export(db, user), indent=2, ensure_ascii=False).encode()


def delete_account(db: Session, user: User) -> None:
    from app.services import calendar as calendar_svc

    try:
        calendar_svc.disconnect(db, user)  # revoke at Google first (best effort)
    except Exception:  # noqa: BLE001 - deletion must not be blocked by a third party
        db.rollback()
    for e in db.execute(select(EmailMessage).where(EmailMessage.user_id == user.id)).scalars():
        e.to_email = "deleted"  # keep delivery stats, drop the address
    db.delete(user)
    db.commit()
