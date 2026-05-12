"""
Celery task for automated monthly attendance synchronisation.

Task: ``sync_all_monthly_attendance``
──────────────────────────────────────
Scheduled via Celery Beat (default: 1st of every month at 03:00 AM IST).
Can also be triggered manually:

    from app.tasks.sync_monthly import sync_all_monthly_attendance
    sync_all_monthly_attendance.delay()          # current month
    sync_all_monthly_attendance.delay(4, 2026)   # specific month

Pipeline:
    1. Query all active employees from the database.
    2. Call COSEC Monthly API with ``range=all`` (bulk fetch).
    3. Validate every record via ``MonthlyAttendanceSyncSchema``.
    4. Upsert into ``attendance_monthly`` via ``sync_monthly_batch()``.
    5. Log summary statistics.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from celery.schedules import crontab

from app.config import get_settings
from app.tasks.sync import celery_app

settings = get_settings()
logger = logging.getLogger(__name__)


# ── Register in Celery Beat schedule ───────────────────────
celery_app.conf.beat_schedule["sync-monthly-attendance-full"] = {
    "task": "app.tasks.sync_monthly.sync_all_monthly_attendance",
    # Run on the 1st of every month at 03:00 AM IST
    "schedule": crontab(hour=3, minute=0, day_of_month=1),
}


@celery_app.task(
    name="app.tasks.sync_monthly.sync_all_monthly_attendance",
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
    acks_late=True,
)
def sync_all_monthly_attendance(
    self,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> dict:
    """
    Celery task: Fetch monthly attendance from the COSEC API for all
    active employees and upsert into ``attendance_monthly``.

    Args:
        month: 1–12.  Defaults to the **previous** month (if run on the
               1st) or the current month.
        year:  4-digit year.  Defaults to current year.

    Returns:
        Dict with sync statistics (JSON-serialisable for Celery backend).
    """
    import asyncio

    async def _sync() -> dict:
        from app.services.matrix_monthly import monthly_service
        from app.crud.crud_monthly import sync_monthly_batch
        from app.database import AsyncSessionLocal

        now = datetime.now()
        target_month = month or now.month
        target_year = year or now.year

        logger.info(
            "Starting monthly attendance sync for %02d/%d",
            target_month,
            target_year,
        )

        # ── Step 1: Fetch from COSEC API (bulk) ────────────
        raw_records = await monthly_service.fetch_monthly_attendance(
            month=target_month,
            year=target_year,
            range_type="all",
        )

        if not raw_records:
            logger.warning(
                "COSEC Monthly API returned 0 records for %02d/%d. "
                "API may be unreachable or month has no data.",
                target_month,
                target_year,
            )
            return {
                "month": target_month,
                "year": target_year,
                "total_fetched": 0,
                "validated": 0,
                "inserted": 0,
                "updated": 0,
                "skipped": 0,
                "errors": 0,
            }

        logger.info(
            "Fetched %d raw monthly records from COSEC API.",
            len(raw_records),
        )

        # ── Step 2: Validate via Pydantic ──────────────────
        validated = monthly_service.validate_records(raw_records)

        if not validated:
            logger.error(
                "All %d raw records failed validation — aborting sync.",
                len(raw_records),
            )
            return {
                "month": target_month,
                "year": target_year,
                "total_fetched": len(raw_records),
                "validated": 0,
                "inserted": 0,
                "updated": 0,
                "skipped": 0,
                "errors": len(raw_records),
            }

        # ── Step 3: Upsert into DB ────────────────────────
        async with AsyncSessionLocal() as db:
            result = await sync_monthly_batch(db, validated, source="API")

        logger.info(
            "Monthly sync complete for %02d/%d — "
            "fetched=%d validated=%d inserted=%d updated=%d "
            "skipped=%d errors=%d",
            target_month,
            target_year,
            result.total_fetched,
            result.validated,
            result.inserted,
            result.updated,
            result.skipped,
            result.errors,
        )

        return {
            "month": target_month,
            "year": target_year,
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
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(_sync())
    except Exception as exc:
        logger.exception(
            "Monthly sync task failed with exception: %s", exc
        )
        # Retry with exponential backoff
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.tasks.sync_monthly.sync_previous_month",
)
def sync_previous_month() -> dict:
    """
    Convenience task: sync the **previous** month's data.
    Useful for the nightly schedule on the 1st of each month.
    """
    now = datetime.now()
    if now.month == 1:
        target_month = 12
        target_year = now.year - 1
    else:
        target_month = now.month - 1
        target_year = now.year

    return sync_all_monthly_attendance(
        month=target_month,
        year=target_year,
    )
