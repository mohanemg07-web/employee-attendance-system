"""
Celery task for automated daily attendance synchronisation.

Task: ``sync_daily_attendance``
────────────────────────────────
Scheduled via Celery Beat (default: daily at 02:00 AM IST — **after**
user master sync at 01:30 AM, **before** monthly summary at 02:30 AM).

Can also be triggered manually::

    from app.tasks.sync_daily import sync_daily_attendance
    sync_daily_attendance.delay()               # yesterday
    sync_daily_attendance.delay("28042026")      # specific date

Pipeline:
    1. Determine the target date (default: yesterday).
    2. Fetch all daily attendance records from COSEC API (bulk, ``range=all``).
    3. Validate every record via ``DailyAttendanceSyncSchema``.
    4. Upsert into ``attendance_logs`` with MANUAL_CSV provenance protection.
    5. Log summary statistics.

Execution Order (IST):
    01:30 AM — sync_all_users (user master)
    02:00 AM — sync_daily_attendance ← THIS TASK
    02:30 AM — sync_monthly_attendance
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from celery.schedules import crontab

from app.config import get_settings
from app.tasks.sync import celery_app

settings = get_settings()
logger = logging.getLogger(__name__)

# ── IST timezone ───────────────────────────────────────────
IST = timezone(timedelta(hours=5, minutes=30))

# ── Distributed lock key ──────────────────────────────────
_LOCK_KEY = "celery:lock:sync_daily_attendance"
_LOCK_TTL = 900  # 15 minutes — max expected runtime

# ── Register in Celery Beat schedule ───────────────────────
celery_app.conf.beat_schedule["sync-daily-attendance"] = {
    "task": "app.tasks.sync_daily.sync_daily_attendance",
    # Run daily at 02:00 AM IST — after user master sync (01:30)
    "schedule": crontab(hour=2, minute=0),
}


def _acquire_redis_lock() -> Optional[object]:
    """
    Acquire a Redis-based distributed lock to prevent concurrent
    execution of the daily attendance sync task.

    Returns the lock object on success, or ``None`` if already locked.
    """
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL)
        lock = r.lock(_LOCK_KEY, timeout=_LOCK_TTL, blocking=False)
        if lock.acquire(blocking=False):
            return lock
        logger.warning(
            "sync_daily_attendance: another instance is already running "
            "(lock key=%s). Skipping this execution.",
            _LOCK_KEY,
        )
        return None
    except Exception as exc:
        # If Redis is unavailable, proceed without locking
        logger.warning(
            "Redis lock unavailable (%s) — proceeding without lock.", exc
        )
        return None


def _release_lock(lock: Optional[object]) -> None:
    """Release a previously acquired Redis lock, ignoring errors."""
    if lock is None:
        return
    try:
        lock.release()  # type: ignore[union-attr]
    except Exception as exc:
        logger.debug("Failed to release Redis lock: %s", exc)


def _parse_target_date(date_str: Optional[str]) -> date:
    """
    Parse a date string in ``ddmmyyyy`` format, or default to yesterday (IST).
    """
    if date_str:
        try:
            return datetime.strptime(date_str, "%d%m%Y").date()
        except ValueError:
            pass
        # Try ISO format
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            pass
        logger.warning(
            "Could not parse target date '%s', defaulting to yesterday.",
            date_str,
        )

    # Default: yesterday in IST
    now_ist = datetime.now(IST)
    return (now_ist - timedelta(days=1)).date()


@celery_app.task(
    name="app.tasks.sync_daily.sync_daily_attendance",
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
    acks_late=True,
)
def sync_daily_attendance(
    self,
    target_date_str: Optional[str] = None,
    end_date_str: Optional[str] = None,
) -> dict:
    """
    Celery task: Fetch daily attendance from the COSEC API and
    upsert into the ``attendance_logs`` table.

    Args:
        target_date_str: Start date in ``ddmmyyyy`` or ``yyyy-mm-dd`` format.
            Defaults to yesterday (IST).
        end_date_str: Optional end date for multi-day sync.
            Defaults to ``target_date_str`` (single day).

    Returns:
        Dict with sync statistics (JSON-serialisable for Celery backend).
    """
    lock = _acquire_redis_lock()

    t_start = time.monotonic()

    start_date = _parse_target_date(target_date_str)
    end_date = _parse_target_date(end_date_str) if end_date_str else start_date

    async def _sync() -> dict:
        from app.services.matrix_daily import daily_attendance_service
        from app.crud.crud_daily import upsert_daily_batch
        from app.database import AsyncSessionLocal

        logger.info(
            "Starting COSEC Daily Attendance sync for %s to %s",
            start_date.isoformat(),
            end_date.isoformat(),
        )

        # ── Step 1: Fetch from COSEC API (bulk) ────────────
        raw_records = await daily_attendance_service.fetch_daily_attendance(
            start_date=start_date,
            end_date=end_date,
        )

        if not raw_records:
            logger.warning(
                "COSEC Daily API returned 0 records for %s to %s. "
                "API may be unreachable or no attendance processed.",
                start_date.isoformat(),
                end_date.isoformat(),
            )
            return {
                "date_range": f"{start_date.isoformat()} to {end_date.isoformat()}",
                "total_fetched": 0,
                "validated": 0,
                "inserted": 0,
                "updated": 0,
                "skipped": 0,
                "errors": 0,
            }

        logger.info(
            "Fetched %d raw daily attendance records from COSEC API.",
            len(raw_records),
        )

        # ── Step 2: Validate via Pydantic ──────────────────
        validated = daily_attendance_service.validate_records(raw_records)

        if not validated:
            logger.error(
                "All %d raw daily records failed validation — aborting.",
                len(raw_records),
            )
            return {
                "date_range": f"{start_date.isoformat()} to {end_date.isoformat()}",
                "total_fetched": len(raw_records),
                "validated": 0,
                "inserted": 0,
                "updated": 0,
                "skipped": 0,
                "errors": len(raw_records),
            }

        # ── Step 3: Upsert into attendance_logs ────────────
        async with AsyncSessionLocal() as db:
            result = await upsert_daily_batch(db, validated)

        logger.info(
            "Daily attendance sync complete for %s to %s — "
            "fetched=%d validated=%d inserted=%d updated=%d "
            "skipped=%d errors=%d",
            start_date.isoformat(),
            end_date.isoformat(),
            result.total_fetched,
            result.validated,
            result.inserted,
            result.updated,
            result.skipped,
            result.errors,
        )

        return {
            "date_range": f"{start_date.isoformat()} to {end_date.isoformat()}",
            "total_fetched": result.total_fetched,
            "validated": result.validated,
            "inserted": result.inserted,
            "updated": result.updated,
            "skipped": result.skipped,
            "errors": result.errors,
            "error_messages": result.error_messages[:20],
        }

    # Run the async pipeline in Celery's sync context
    try:
        result = asyncio.run(_sync())
        elapsed = time.monotonic() - t_start
        logger.info(
            "sync_daily_attendance completed in %.2f seconds.", elapsed
        )
        return result
    except Exception as exc:
        elapsed = time.monotonic() - t_start
        logger.exception(
            "Daily attendance sync task failed after %.2fs: %s",
            elapsed,
            exc,
        )
        raise self.retry(exc=exc)
    finally:
        _release_lock(lock)
