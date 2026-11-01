"""Durable background jobs stored in the `jobs` table (no Redis/Celery needed).

- `enqueue` is idempotent on `idempotency_key`: scheduling the same report twice is a no-op.
- `run_due` claims jobs with SELECT … FOR UPDATE SKIP LOCKED on PostgreSQL, so several workers can
  run side by side without double-processing (SQLite, used in tests, simply ignores the hint).
- Failures retry with exponential backoff (1, 2, 4, 8 … minutes); after `max_attempts` a job is
  marked `dead` and left for inspection. A job whose worker crashed is released after 15 minutes.
- Payloads hold ids only — never codes, tokens or health data.
"""

import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.billing import Job

logger = logging.getLogger("app.jobs")

STALE_LOCK = timedelta(minutes=15)
HANDLERS: dict[str, Callable[[Session, dict], None]] = {}


class PermanentJobError(Exception):
    """Retrying won't help (e.g. the user was deleted): mark the job finished without retries."""


def handler(kind: str):
    def register(fn: Callable[[Session, dict], None]):
        HANDLERS[kind] = fn
        return fn
    return register


def enqueue(db: Session, kind: str, payload: dict, *, idempotency_key: str | None = None,
            run_after: datetime | None = None, max_attempts: int = 5) -> Job:
    if idempotency_key:
        existing = db.execute(select(Job).where(Job.idempotency_key == idempotency_key)).scalar_one_or_none()
        if existing is not None:
            return existing
    job = Job(kind=kind, payload=payload, idempotency_key=idempotency_key, run_after=run_after or utcnow(),
              max_attempts=max_attempts)
    db.add(job)
    try:
        db.commit()
    except IntegrityError:  # enqueued concurrently
        db.rollback()
        return db.execute(select(Job).where(Job.idempotency_key == idempotency_key)).scalar_one()
    return job


def _claim(db: Session) -> Job | None:
    now = utcnow()
    job = db.execute(
        select(Job).where(Job.status == "queued", Job.run_after <= now).order_by(Job.run_after).limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if job is None:
        return None
    job.status, job.locked_at, job.attempts = "running", now, job.attempts + 1
    db.commit()
    return job


def release_stale(db: Session) -> int:
    res = db.execute(update(Job).where(Job.status == "running", Job.locked_at < utcnow() - STALE_LOCK)
                     .values(status="queued", locked_at=None))
    db.commit()
    return res.rowcount or 0


def run_one(db: Session) -> bool:
    """Runs a single due job. Returns False when there was nothing to do."""
    job = _claim(db)
    if job is None:
        return False
    fn = HANDLERS.get(job.kind)
    try:
        if fn is None:
            raise PermanentJobError(f"no handler for {job.kind}")
        fn(db, dict(job.payload or {}))
    except PermanentJobError as exc:
        db.rollback()
        job = db.get(Job, job.id)
        job.status, job.last_error, job.finished_at = "dead", str(exc)[:500], utcnow()
        db.commit()
        logger.warning("Job %s (%s) dropped: %s", job.id, job.kind, exc)
        return True
    except Exception as exc:
        db.rollback()
        job = db.get(Job, job.id)
        job.last_error = f"{type(exc).__name__}: {exc}"[:500]
        if job.attempts >= job.max_attempts:
            job.status, job.finished_at = "dead", utcnow()
            logger.error("Job %s (%s) dead after %s attempts", job.id, job.kind, job.attempts)
        else:
            job.status, job.locked_at = "queued", None
            job.run_after = utcnow() + timedelta(minutes=2 ** (job.attempts - 1))
        db.commit()
        return True
    job.status, job.finished_at, job.last_error = "succeeded", utcnow(), None
    db.commit()
    return True


def run_due(db: Session, limit: int = 50) -> int:
    done = 0
    while done < limit and run_one(db):
        done += 1
    return done


def get(db: Session, job_id: uuid.UUID) -> Job | None:
    return db.get(Job, job_id)
