"""
Celery application and background tasks for attendance data synchronisation.

Schedule:
- sync_yesterday_attendance: Runs nightly at 02:00 AM
- sync_monthly_summary: Runs nightly at 02:30 AM
"""
import logging
from datetime import datetime, timedelta

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# ── Celery App ──────────────────────────────────────────
celery_app = Celery(
    "attendance_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    beat_schedule={
        "sync-yesterday-daily": {
            "task": "app.tasks.sync.sync_yesterday_attendance",
            "schedule": crontab(hour=2, minute=0),
        },
        "sync-monthly-summary": {
            "task": "app.tasks.sync.sync_monthly_summary",
            "schedule": crontab(hour=2, minute=30),
        },
    },
)


@celery_app.task(name="app.tasks.sync.sync_yesterday_attendance")
def sync_yesterday_attendance():
    """
    Nightly task: fetch yesterday's daily attendance from COSEC API
    and upsert into the database.

    Conflict resolution: skips records where data_source = 'MANUAL_CSV'.
    """
    import asyncio
    from app.services.matrix_cosec import cosec_service
    from app.database import AsyncSessionLocal

    async def _sync():
        yesterday = (datetime.now() - timedelta(days=1))
        date_str = yesterday.strftime("%d/%m/%Y")

        logger.info(f"Starting daily sync for {yesterday.date()}")

        raw_records = await cosec_service.fetch_daily_attendance(
            start_date=date_str,
            end_date=date_str,
        )
        logger.info(f"Fetched {len(raw_records)} records from COSEC API")

        async with AsyncSessionLocal() as db:
            result = await cosec_service.sync_to_database(db, raw_records)
            logger.info(
                "Sync complete: inserted=%d updated=%d skipped=%d errors=%d",
                result.inserted,
                result.updated,
                result.skipped,
                result.errors,
            )
            return {
                "inserted": result.inserted,
                "updated": result.updated,
                "skipped": result.skipped,
                "errors": result.errors,
            }

    return asyncio.run(_sync())


@celery_app.task(name="app.tasks.sync.sync_monthly_summary")
def sync_monthly_summary():
    """
    Nightly task: fetch current month's attendance summary from COSEC API
    and update the monthly aggregation table.
    """
    import asyncio
    from app.services.matrix_cosec import cosec_service
    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    async def _sync():
        now = datetime.now()
        month_year = now.strftime("%m%Y")

        logger.info(f"Starting monthly sync for {month_year}")

        records = await cosec_service.fetch_monthly_attendance(month_year)
        logger.info(f"Fetched {len(records)} monthly records from COSEC API")

        async with AsyncSessionLocal() as db:
            for record in records:
                emp_code = record.get("user-id", "") or record.get("Employee-ID", "")
                emp_result = await db.execute(
                    text("SELECT id FROM employees WHERE employee_code = :code"),
                    {"code": emp_code},
                )
                emp_row = emp_result.fetchone()
                if not emp_row:
                    continue

                employee_id = emp_row[0]

                await db.execute(
                    text("""
                        INSERT INTO attendance_monthly
                            (employee_id, month, year,
                             total_present, total_absent, total_late,
                             total_half_day, total_leave, data_source)
                        VALUES
                            (:eid, :month, :year,
                             :present, :absent, :late,
                             :half_day, :leave, 'API')
                        ON CONFLICT (employee_id, month, year)
                        DO UPDATE SET
                            total_present = EXCLUDED.total_present,
                            total_absent = EXCLUDED.total_absent,
                            total_late = EXCLUDED.total_late,
                            total_half_day = EXCLUDED.total_half_day,
                            total_leave = EXCLUDED.total_leave,
                            updated_at = NOW()
                        WHERE attendance_monthly.data_source != 'MANUAL_CSV'
                    """),
                    {
                        "eid": employee_id,
                        "month": now.month,
                        "year": now.year,
                        "present": int(record.get("present-days", 0)),
                        "absent": int(record.get("absent-days", 0)),
                        "late": int(record.get("late-days", 0)),
                        "half_day": int(record.get("half-days", 0)),
                        "leave": int(record.get("leave-days", 0)),
                    },
                )
            await db.commit()
            logger.info("Monthly sync complete")

    return asyncio.run(_sync())
