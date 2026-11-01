"""Background worker: runs queued jobs, schedules report emails, tidies old records.

    python -m app.worker           # run forever (production: one or more of these next to the API)
    python -m app.worker --once    # one pass, then exit (cron / debugging)

Stops cleanly on SIGINT/SIGTERM after the current job.
"""

import argparse
import logging
import signal
import time

from app.db.session import SessionLocal
from app.services import jobs, notifications

logger = logging.getLogger("app.worker")
_stop = False


def _handle_stop(*_):
    global _stop
    _stop = True


def tick(*, schedule: bool, maintain: bool) -> int:
    with SessionLocal() as db:
        jobs.release_stale(db)
        if schedule:
            notifications.schedule_due_reports(db)
        if maintain:
            notifications.maintenance(db)
        return jobs.run_due(db)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    if args.once:
        logger.info("Processed %s job(s)", tick(schedule=True, maintain=True))
        return
    logger.info("Worker started")
    last_schedule = last_maintenance = 0.0
    while not _stop:
        now = time.monotonic()
        schedule, maintain = now - last_schedule >= 60, now - last_maintenance >= 3600
        try:
            done = tick(schedule=schedule, maintain=maintain)
        except Exception:  # keep the worker alive; the error is logged and retried next tick
            logger.exception("Worker tick failed")
            done = 0
        last_schedule = now if schedule else last_schedule
        last_maintenance = now if maintain else last_maintenance
        if not done:
            time.sleep(args.poll_seconds)
    logger.info("Worker stopped")


if __name__ == "__main__":
    main()
