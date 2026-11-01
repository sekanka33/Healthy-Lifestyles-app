"""Fixed-window rate limiting stored in the database (shared by all workers, no Redis needed)."""

from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import as_utc, utcnow
from app.models.user import RateLimitBucket


def hit(db: Session, key: str, *, limit: int, window_seconds: int) -> None:
    """Count one attempt for `key`; raise 429 once `limit` is exceeded within the window."""
    now = utcnow()
    bucket = db.execute(select(RateLimitBucket).where(RateLimitBucket.key == key).with_for_update()).scalar_one_or_none()
    if bucket is None:
        db.add(RateLimitBucket(key=key, window_start=now, count=1))
        try:
            db.commit()
            return
        except IntegrityError:  # another request created the bucket first — count against it
            db.rollback()
            return hit(db, key, limit=limit, window_seconds=window_seconds)
    window_start = as_utc(bucket.window_start)
    if now - window_start >= timedelta(seconds=window_seconds):
        bucket.window_start, bucket.count = now, 1
        db.commit()
        return
    if bucket.count >= limit:
        retry_after = int((window_start + timedelta(seconds=window_seconds) - now).total_seconds()) + 1
        db.rollback()
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            {"code": "rate_limited", "message": "Too many attempts. Please try again later."},
            headers={"Retry-After": str(max(retry_after, 1))},
        )
    bucket.count += 1
    db.commit()


def reset(db: Session, key: str) -> None:
    bucket = db.get(RateLimitBucket, key)
    if bucket is not None:
        db.delete(bucket)
        db.commit()
