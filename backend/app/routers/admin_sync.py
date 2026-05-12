"""
Admin Sync Router — manual sync triggers and monitoring endpoints.

Provides ADMIN-only endpoints for:
    - Triggering manual user/daily/monthly syncs
    - Viewing sync history and status
    - Checking scheduler health

All endpoints require ADMIN role authentication.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.employee import Employee
from app.utils.security import require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/sync", tags=["Admin Sync"])


# ── Manual Sync Triggers ──────────────────────────────────


@router.post("/users")
async def trigger_user_sync(
    current_user: Employee = Depends(require_role("ADMIN")),
):
    """
    Trigger a manual user master sync from Matrix COSEC API.

    Fetches all active users and upserts into the employees table.
    Resolves manager hierarchy from reporting-incharge fields.
    """
    from app.services.sync_orchestrator import sync_orchestrator

    result = await sync_orchestrator.sync_users(triggered_by="MANUAL")
    return {
        "message": "User sync completed",
        "result": result,
    }


@router.post("/daily")
async def trigger_daily_sync(
    start_date: Optional[str] = Query(
        None,
        description="Start date in YYYY-MM-DD format. Defaults to yesterday.",
    ),
    end_date: Optional[str] = Query(
        None,
        description="End date in YYYY-MM-DD format. Defaults to start_date.",
    ),
    current_user: Employee = Depends(require_role("ADMIN")),
):
    """
    Trigger a manual daily attendance sync from Matrix COSEC API.

    Fetches attendance records for the specified date range and
    upserts into attendance_logs. Protects MANUAL_CSV records.
    """
    from app.services.sync_orchestrator import sync_orchestrator

    # Parse dates
    start = None
    end = None
    if start_date:
        try:
            start = date.fromisoformat(start_date)
        except ValueError:
            return {"error": f"Invalid start_date format: {start_date}. Use YYYY-MM-DD."}
    if end_date:
        try:
            end = date.fromisoformat(end_date)
        except ValueError:
            return {"error": f"Invalid end_date format: {end_date}. Use YYYY-MM-DD."}

    result = await sync_orchestrator.sync_daily(
        start_date=start,
        end_date=end or start,
        triggered_by="MANUAL",
    )
    return {
        "message": "Daily attendance sync completed",
        "result": result,
    }


@router.post("/monthly")
async def trigger_monthly_sync(
    month: Optional[int] = Query(
        None, ge=1, le=12,
        description="Month (1-12). Defaults to current month.",
    ),
    year: Optional[int] = Query(
        None, ge=2000, le=2100,
        description="Year (4-digit). Defaults to current year.",
    ),
    current_user: Employee = Depends(require_role("ADMIN")),
):
    """
    Trigger a manual monthly attendance sync from Matrix COSEC API.

    Fetches monthly summaries and upserts into attendance_monthly.
    Protects MANUAL_CSV records.
    """
    from app.services.sync_orchestrator import sync_orchestrator

    result = await sync_orchestrator.sync_monthly(
        month=month,
        year=year,
        triggered_by="MANUAL",
    )
    return {
        "message": "Monthly attendance sync completed",
        "result": result,
    }


# ── Sync Status / Monitoring ──────────────────────────────


@router.get("/status")
async def get_sync_status(
    limit: int = Query(20, ge=1, le=100, description="Number of recent logs"),
    sync_type: Optional[str] = Query(
        None, description="Filter by type: USER, DAILY, MONTHLY"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(require_role("ADMIN")),
):
    """
    List recent sync logs with timing and record counts.
    """
    query = "SELECT * FROM sync_logs"
    params = {"limit": limit}

    if sync_type:
        query += " WHERE sync_type = :sync_type"
        params["sync_type"] = sync_type.upper()

    query += " ORDER BY started_at DESC LIMIT :limit"

    result = await db.execute(text(query), params)
    rows = result.fetchall()
    columns = result.keys()

    logs = []
    for row in rows:
        log_dict = dict(zip(columns, row))
        # Convert datetime objects to ISO strings for JSON serialization
        for key in ("started_at", "completed_at"):
            val = log_dict.get(key)
            if val and isinstance(val, datetime):
                log_dict[key] = val.isoformat()
        logs.append(log_dict)

    return {
        "total": len(logs),
        "logs": logs,
    }


@router.get("/status/{log_id}")
async def get_sync_log_detail(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(require_role("ADMIN")),
):
    """
    Get detailed sync log for a specific sync operation.
    """
    result = await db.execute(
        text("SELECT * FROM sync_logs WHERE id = :id"),
        {"id": log_id},
    )
    row = result.fetchone()

    if not row:
        return {"error": "Sync log not found"}

    columns = result.keys()
    log_dict = dict(zip(columns, row))

    for key in ("started_at", "completed_at"):
        val = log_dict.get(key)
        if val and isinstance(val, datetime):
            log_dict[key] = val.isoformat()

    return {"log": log_dict}


@router.get("/scheduler")
async def get_scheduler_status(
    current_user: Employee = Depends(require_role("ADMIN")),
):
    """
    Check the background scheduler health and list scheduled jobs.
    """
    try:
        from app.services.sync_scheduler import get_scheduler
        scheduler = get_scheduler()

        if not scheduler:
            return {
                "status": "not_started",
                "message": "Scheduler has not been started",
                "jobs": [],
            }

        if not scheduler.running:
            return {
                "status": "stopped",
                "message": "Scheduler is not running",
                "jobs": [],
            }

        jobs = []
        for job in scheduler.get_jobs():
            next_run = job.next_run_time
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": next_run.isoformat() if next_run else None,
                "trigger": str(job.trigger),
            })

        return {
            "status": "running",
            "jobs": jobs,
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": str(exc),
            "jobs": [],
        }
