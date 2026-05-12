"""
Monthly attendance aggregation service.

Computes and upserts monthly summaries into ``attendance_monthly``
from daily ``attendance_logs``. Designed to be idempotent — safe to
re-run any number of times for the same (employee, month, year).

Business rules:
    - Official login: 09:00 IST
    - Minimum work hours: 8 hours
    - Late = first_in > 09:00
    - Sundays and HOLIDAY/WEEKEND statuses are excluded (Saturday is a working day)
    - NULL first_in on a working day → ABSENT
    - HALF_DAY increments total_half_day only (use ½-day in scores via ``total_half_day``)
"""
from __future__ import annotations

import logging
from calendar import monthrange
from datetime import date as dt_date
from datetime import timedelta
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.attendance import AttendanceLog, AttendanceMonthly

logger = logging.getLogger(__name__)

# Statuses that are excluded from working-day counts
_NON_WORKING_STATUSES = {"WEEKEND", "HOLIDAY"}


async def aggregate_monthly_attendance(
    db: AsyncSession,
    employee_id: int,
    month: int,
    year: int,
) -> Optional[AttendanceMonthly]:
    """
    Aggregate daily logs for a single employee into a monthly summary.

    This is **idempotent**: it deletes any existing row for the same
    (employee_id, month, year) and inserts a fresh one.

    Args:
        db: Async database session (caller manages commit).
        employee_id: Target employee ID.
        month: Calendar month (1-12).
        year: Calendar year.

    Returns:
        The upserted ``AttendanceMonthly`` instance, or None if no logs exist.
    """
    existing_m = await db.execute(
        select(AttendanceMonthly).where(
            AttendanceMonthly.employee_id == employee_id,
            AttendanceMonthly.month == month,
            AttendanceMonthly.year == year,
        )
    )
    protected = existing_m.scalar_one_or_none()
    if protected is not None and protected.data_source == "MANUAL_CSV":
        logger.info(
            "Skip monthly aggregation emp=%d %d/%d — MANUAL_CSV summary protected.",
            employee_id, month, year,
        )
        return protected

    first_d = dt_date(year, month, 1)
    last_d = dt_date(year, month, monthrange(year, month)[1])
    result = await db.execute(
        select(AttendanceLog).where(
            AttendanceLog.employee_id == employee_id,
            AttendanceLog.log_date >= first_d,
            AttendanceLog.log_date <= last_d,
        )
    )
    all_logs = result.scalars().all()

    logs = [
        log for log in all_logs
        if log.status not in _NON_WORKING_STATUSES
    ]

    if not logs:
        # No working-day logs for this month — nothing to aggregate.
        # Existing stale monthly rows will be overwritten on next CSV upload.
        return None

    # ── Compute aggregates ────────────────────────────────
    total_present = 0
    total_absent = 0
    total_late = 0
    total_half_day = 0
    total_leave = 0
    work_hours_seconds: List[float] = []

    for log in logs:
        status = (log.status or "").upper()

        if status == "PRESENT":
            total_present += 1
        elif status == "ABSENT":
            total_absent += 1
        elif status == "HALF_DAY":
            total_half_day += 1
        elif status == "ON_LEAVE":
            total_leave += 1
        elif status == "LATE":
            # LATE is its own category — do NOT count as present here.
            # Downstream formulas use (total_present + total_late) for "days attended".
            total_late += 1
        else:
            # Unknown status — treat as absent if no punch
            if log.first_in is None:
                total_absent += 1
            else:
                total_present += 1

        # NOTE: is_late flag is a secondary attribute on PRESENT logs.
        # It does NOT increment total_late — only status == "LATE" does.
        # This prevents double-counting in days_present = total_present + total_late.

        # Accumulate work hours
        if log.gross_work_hrs is not None:
            if isinstance(log.gross_work_hrs, timedelta):
                work_hours_seconds.append(log.gross_work_hrs.total_seconds())

    # Average work hours
    avg_work_hrs = None
    if work_hours_seconds:
        avg_seconds = sum(work_hours_seconds) / len(work_hours_seconds)
        avg_work_hrs = timedelta(seconds=int(avg_seconds))

    # ── Upsert: select + update or insert (cross-DB compatible) ─
    existing_row = await db.execute(
        select(AttendanceMonthly).where(
            AttendanceMonthly.employee_id == employee_id,
            AttendanceMonthly.month == month,
            AttendanceMonthly.year == year,
        )
    )
    monthly = existing_row.scalar_one_or_none()

    if monthly:
        # Update existing
        monthly.total_present = total_present
        monthly.total_absent = total_absent
        monthly.total_late = total_late
        monthly.total_half_day = total_half_day
        monthly.total_leave = total_leave
        monthly.avg_work_hrs = avg_work_hrs
        monthly.data_source = "AGGREGATED"
    else:
        # Insert new
        monthly = AttendanceMonthly(
            employee_id=employee_id,
            month=month,
            year=year,
            total_present=total_present,
            total_absent=total_absent,
            total_late=total_late,
            total_half_day=total_half_day,
            total_leave=total_leave,
            avg_work_hrs=avg_work_hrs,
            data_source="AGGREGATED",
        )
        db.add(monthly)

    logger.info(
        "Aggregated monthly: emp=%d %d/%d → P=%d A=%d L=%d HD=%d LV=%d",
        employee_id, month, year,
        total_present, total_absent, total_late, total_half_day, total_leave,
    )

    return monthly


async def aggregate_monthly_for_all(
    db: AsyncSession,
    month: int,
    year: int,
) -> int:
    """
    Run monthly aggregation for ALL active employees.

    Args:
        db: Async database session.
        month: Calendar month (1-12).
        year: Calendar year.

    Returns:
        Number of employees aggregated.
    """
    result = await db.execute(
        select(Employee.id).where(Employee.is_active == True)
    )
    employee_ids = [row[0] for row in result.fetchall()]

    count = 0
    for emp_id in employee_ids:
        summary = await aggregate_monthly_attendance(db, emp_id, month, year)
        if summary:
            count += 1

    await db.commit()

    logger.info(
        "Monthly aggregation complete for %d/%d: %d employees processed",
        month, year, count,
    )
    return count


async def aggregate_for_affected_months(
    db: AsyncSession,
    employee_ids: List[int],
    months: set,
) -> int:
    """
    Run aggregation for specific employees and months.

    Called after CSV upload to re-aggregate only the affected data.

    Args:
        db: Async database session.
        employee_ids: List of affected employee IDs.
        months: Set of (month, year) tuples.

    Returns:
        Number of summaries upserted.
    """
    count = 0
    for emp_id in employee_ids:
        for month, year in months:
            summary = await aggregate_monthly_attendance(db, emp_id, month, year)
            if summary:
                count += 1

    # Caller is responsible for commit
    return count
