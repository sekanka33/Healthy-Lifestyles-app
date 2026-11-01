"""Plan resolution. The server-side entitlement row is the only source of truth (Phase 5 writes it
from verified RevenueCat data); nothing the client sends can change the result."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import as_utc, utcnow
from app.models.billing import SubscriptionEntitlement
from app.models.user import User

ACTIVE_STATUSES = ("active", "grace_period", "cancelled")  # cancelled = won't renew, still paid up


def is_premium(db: Session, user: User) -> bool:
    ent = db.execute(
        select(SubscriptionEntitlement).where(
            SubscriptionEntitlement.user_id == user.id,
            SubscriptionEntitlement.entitlement == get_settings().revenuecat_premium_entitlement,
        )
    ).scalar_one_or_none()
    if ent is None or ent.status not in ACTIVE_STATUSES:
        return False
    return ent.expires_at is None or as_utc(ent.expires_at) > utcnow()


def plan(db: Session, user: User) -> str:
    return "premium" if is_premium(db, user) else "free"
