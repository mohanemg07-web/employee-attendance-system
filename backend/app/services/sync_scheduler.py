"""
APScheduler-based background sync scheduler.

Provides an in-process async scheduler that runs biometric sync jobs
without requiring Celery or Redis infrastructure.

Schedule:
    - User master sync:      Daily at 01:00 AM IST
    - Daily attendance sync: Every SYNC_INTERVAL_MINUTES (default 15 min)
    - Monthly summary sync:  Daily at 02:00 AM IST

The scheduler starts/stops with the FastAPI lifespan and uses
AsyncIOScheduler to work natively with the async event loop.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import get_settings

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _job_sync_users():
    """Scheduled job: sync user master data from COSEC API."""
    logger.info("[SCHEDULER] Starting user master sync...")
    try:
        from app.services.sync_orchestrator import sync_orchestrator
        result = await sync_orchestrator.sync_users(triggered_by="SCHEDULER")
        logger.info("[SCHEDULER] User sync result: %s", result.get("status"))
    except Exception:
        logger.exception("[SCHEDULER] User sync job failed")


async def _job_sync_daily():
    """Scheduled job: sync today + yesterday's attendance from COSEC API.

    Syncs both dates so that real-time punches appear within the
    SYNC_INTERVAL_MINUTES window, while also catching any late
    punch-outs from the previous day.
    """
    logger.info("[SCHEDULER] Starting daily attendance sync (today + yesterday)...")
    try:
        from app.services.sync_orchestrator import sync_orchestrator
        today = date.today()
        yesterday = today - timedelta(days=1)
        result = await sync_orchestrator.sync_daily(
            start_date=yesterday,
            end_date=today,
            triggered_by="SCHEDULER",
        )
        logger.info("[SCHEDULER] Daily sync result: %s", result.get("status"))
    except Exception:
        logger.exception("[SCHEDULER] Daily sync job failed")


async def _job_sync_monthly():
    """Scheduled job: sync current month's attendance summary."""
    logger.info("[SCHEDULER] Starting monthly attendance sync...")
    try:
        from app.services.sync_orchestrator import sync_orchestrator
        result = await sync_orchestrator.sync_monthly(
            triggered_by="SCHEDULER"
        )
        logger.info(
            "[SCHEDULER] Monthly sync result: %s", result.get("status")
        )
    except Exception:
        logger.exception("[SCHEDULER] Monthly sync job failed")


def start_scheduler() -> AsyncIOScheduler:
    """
    Create, configure, and start the APScheduler.

    Called during FastAPI lifespan startup.
    Returns the scheduler instance for shutdown management.
    """
    global _scheduler

    settings = get_settings()
    sync_interval = getattr(settings, "SYNC_INTERVAL_MINUTES", 15)

    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

    # ── User Master Sync: daily at 01:00 AM IST ────────────
    scheduler.add_job(
        _job_sync_users,
        trigger=CronTrigger(hour=1, minute=0),
        id="sync_users_daily",
        name="User Master Sync (Daily)",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # ── Daily Attendance Sync: every N minutes ─────────────
    scheduler.add_job(
        _job_sync_daily,
        trigger=IntervalTrigger(minutes=sync_interval),
        id="sync_daily_attendance",
        name=f"Daily Attendance Sync (every {sync_interval}min)",
        replace_existing=True,
        misfire_grace_time=120,
    )

    # ── Monthly Summary Sync: daily at 02:00 AM IST ───────
    scheduler.add_job(
        _job_sync_monthly,
        trigger=CronTrigger(hour=2, minute=0),
        id="sync_monthly_summary",
        name="Monthly Summary Sync (Daily)",
        replace_existing=True,
        misfire_grace_time=300,
    )

    scheduler.start()
    _scheduler = scheduler

    jobs = scheduler.get_jobs()
    logger.info(
        "[SCHEDULER] Started with %d jobs: %s",
        len(jobs),
        [j.name for j in jobs],
    )

    return scheduler


def stop_scheduler():
    """Gracefully shut down the scheduler during FastAPI shutdown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[SCHEDULER] Stopped gracefully")
        _scheduler = None


def get_scheduler() -> AsyncIOScheduler | None:
    """Return the current scheduler instance (or None if not started)."""
    return _scheduler
