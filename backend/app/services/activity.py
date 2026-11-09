"""Records that a user was active today. Called from the app's auth dependency, so it must be cheap
and must never break a request: at most one write per user per day per process."""

import logging
import uuid
from datetime import date
from threading import Lock

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.analytics import UserActivityDay

logger = logging.getLogger("app.activity")

_seen: set[tuple[uuid.UUID, date]] = set()
_seen_day: date | None = None
_lock = Lock()


def _already_recorded(key: tuple[uuid.UUID, date]) -> bool:
    global _seen_day
    with _lock:
        if _seen_day != key[1]:  # new day: forget yesterday
            _seen.clear()
            _seen_day = key[1]
        if key in _seen:
            return True
        _seen.add(key)
        return False


def forget() -> None:
    """Test helper: clear the in-process memo."""
    global _seen_day
    with _lock:
        _seen.clear()
        _seen_day = None


def record(db: Session, user_id: uuid.UUID) -> None:
    key = (user_id, utcnow().date())
    if _already_recorded(key):
        return
    try:
        exists = db.execute(select(UserActivityDay.user_id).where(
            UserActivityDay.user_id == key[0], UserActivityDay.day == key[1])).first()
        if not exists:
            db.add(UserActivityDay(user_id=key[0], day=key[1]))
            db.commit()
    except SQLAlchemyError:  # e.g. a concurrent insert of the same row: already recorded, fine
        db.rollback()
        logger.debug("activity row for %s already present", key[0])
