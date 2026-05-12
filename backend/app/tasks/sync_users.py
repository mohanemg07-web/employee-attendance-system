"""
Celery task for automated employee / user master synchronisation.

Task: ``sync_all_users``
─────────────────────────
Scheduled via Celery Beat (default: daily at 01:30 AM IST — **before**
attendance sync tasks at 02:00/02:30 AM).

Can also be triggered manually::

    from app.tasks.sync_users import sync_all_users
    sync_all_users.delay()

Pipeline:
    1. Fetch all active users from COSEC User Master API (bulk, ``range=all``).
    2. Validate every record via ``UserMasterSyncSchema``.
    3. Pass 1: Upsert into ``employees`` table.
    4. Pass 2: Resolve ``manager_code`` → ``manager_id`` for hierarchy.
    5. Log summary statistics.

Execution Order:
    This task MUST run **before** daily/monthly attendance sync tasks,
    since attendance records reference ``employees.id`` via FK.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from celery.schedules import crontab

from app.config import get_settings
from app.tasks.sync import celery_app

settings = get_settings()
logger = logging.getLogger(__name__)

# ── Distributed lock key ──────────────────────────────────
_LOCK_KEY = "celery:lock:sync_all_users"
_LOCK_TTL = 600  # 10 minutes — max expected runtime

# ── Register in Celery Beat schedule ───────────────────────
celery_app.conf.beat_schedule["sync-user-master"] = {
    "task": "app.tasks.sync_users.sync_all_users",
    # Run daily at 01:30 AM IST — 30 min BEFORE attendance sync
    "schedule": crontab(hour=1, minute=30),
}


def _acquire_redis_lock() -> Optional[object]:
    """
    Acquire a Redis-based distributed lock to prevent concurrent
    execution of the user sync task.

    Returns the lock object on success, or ``None`` if already locked.
    """
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL)
        lock = r.lock(_LOCK_KEY, timeout=_LOCK_TTL, blocking=False)
        if lock.acquire(blocking=False):
            return lock
        logger.warning(
            "sync_all_users: another instance is already running "
            "(lock key=%s). Skipping this execution.",
            _LOCK_KEY,
        )
        return None
    except Exception as exc:
        # If Redis is unavailable, proceed without locking
        # (better to sync with a small race risk than to skip)
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


@celery_app.task(
    name="app.tasks.sync_users.sync_all_users",
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
    acks_late=True,
)
def sync_all_users(self, active_only: bool = True) -> dict:
    """
    Celery task: Fetch all users from the COSEC User Master API
    and sync into the ``employees`` table with full hierarchy linking.

    Args:
        active_only: When ``True`` (default), only syncs active users
            (COSEC ``active == '1'``).

    Returns:
        Dict with sync statistics (JSON-serialisable for Celery backend).
    """
    lock = _acquire_redis_lock()
    # If we got a lock object, another instance check passed.
    # If lock is None due to Redis error, we still proceed.

    t_start = time.monotonic()

    async def _sync() -> dict:
        from app.services.matrix_user_master import user_master_service
        from app.crud.crud_user import sync_users_full
        from app.database import AsyncSessionLocal

        logger.info(
            "Starting COSEC User Master sync (active_only=%s)",
            active_only,
        )

        # ── Step 1: Fetch from COSEC API (bulk) ────────────
        raw_records = await user_master_service.fetch_all_users(
            active_only=active_only,
        )

        if not raw_records:
            logger.warning(
                "COSEC User Master API returned 0 records. "
                "API may be unreachable or no users configured."
            )
            return {
                "total_fetched": 0,
                "validated": 0,
                "inserted": 0,
                "updated": 0,
                "skipped": 0,
                "manager_links_set": 0,
                "manager_links_failed": 0,
                "errors": 0,
            }

        logger.info(
            "Fetched %d raw user records from COSEC API.",
            len(raw_records),
        )

        # ── Step 2: Validate via Pydantic ──────────────────
        validated = user_master_service.validate_records(raw_records)

        if not validated:
            logger.error(
                "All %d raw user records failed validation — aborting.",
                len(raw_records),
            )
            return {
                "total_fetched": len(raw_records),
                "validated": 0,
                "inserted": 0,
                "updated": 0,
                "skipped": 0,
                "manager_links_set": 0,
                "manager_links_failed": 0,
                "errors": len(raw_records),
            }

        # ── Step 3 & 4: Two-pass upsert + hierarchy ───────
        async with AsyncSessionLocal() as db:
            result = await sync_users_full(db, validated)

        logger.info(
            "User Master sync complete — "
            "fetched=%d validated=%d inserted=%d updated=%d "
            "manager_links=%d link_failures=%d errors=%d",
            result.total_fetched,
            result.validated,
            result.inserted,
            result.updated,
            result.manager_links_set,
            result.manager_links_failed,
            result.errors,
        )

        return {
            "total_fetched": result.total_fetched,
            "validated": result.validated,
            "inserted": result.inserted,
            "updated": result.updated,
            "skipped": result.skipped,
            "manager_links_set": result.manager_links_set,
            "manager_links_failed": result.manager_links_failed,
            "errors": result.errors,
            "error_messages": result.error_messages[:20],
        }

    # Run the async pipeline in Celery's sync context
    # Using asyncio.run() — safe for Python 3.10+ (replaces
    # deprecated asyncio.get_event_loop().run_until_complete())
    try:
        result = asyncio.run(_sync())
        elapsed = time.monotonic() - t_start
        logger.info(
            "sync_all_users completed in %.2f seconds.", elapsed
        )
        return result
    except Exception as exc:
        elapsed = time.monotonic() - t_start
        logger.exception(
            "User Master sync task failed after %.2fs: %s",
            elapsed,
            exc,
        )
        raise self.retry(exc=exc)
    finally:
        _release_lock(lock)
