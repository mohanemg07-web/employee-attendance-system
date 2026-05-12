"""
Attendance score computation and insights generation engine.

All values are computed dynamically — **never stored in DB**.
Called by the dashboard API to enrich responses.

Score formula:
    score = 0.5 * attendance_pct + 0.3 * punctuality + 0.2 * consistency

Insights are rule-based, generated from daily logs and monthly aggregates.
"""
from __future__ import annotations

import logging
import statistics
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceLog, AttendanceMonthly

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
OFFICIAL_LOGIN = time(9, 0)  # 09:00 AM


def _working_days_in_month(month: int, year: int) -> int:
    """Count working days (Mon-Sat) in a given month. Sunday is the only holiday."""
    import calendar
    count = 0
    _, num_days = calendar.monthrange(year, month)
    for day in range(1, num_days + 1):
        d = date(year, month, day)
        if d > date.today():
            break
        if d.weekday() < 6:  # Mon-Sat (Sunday = 6 is excluded)
            count += 1
    return count


async def compute_score(
    db: AsyncSession,
    employee_id: int,
    month: int,
    year: int,
) -> Dict[str, Any]:
    """
    Compute attendance score for an employee for a given month.

    Returns:
        Dict with overall score and component breakdown.
    """
    # Get monthly summary
    result = await db.execute(
        select(AttendanceMonthly).where(
            AttendanceMonthly.employee_id == employee_id,
            AttendanceMonthly.month == month,
            AttendanceMonthly.year == year,
        )
    )
    monthly = result.scalar_one_or_none()

    working_days = _working_days_in_month(month, year)

    if not monthly or working_days == 0:
        return {
            "overall": 0,
            "attendance_pct": 0,
            "punctuality": 0,
            "consistency": 0,
            "working_days": working_days,
        }

    # ── Business rule: Score formula ───────────────────
    # Attendance Score = (PRESENT + LATE × 0.65) / WORKING_DAYS × 100
    LATE_PENALTY_WEIGHT = 0.65

    total_present = monthly.total_present or 0   # COUNT(status='PRESENT')
    total_late = monthly.total_late or 0          # COUNT(status='LATE')
    total_half_day = monthly.total_half_day or 0

    # ── Attendance Score (single canonical formula) ──────
    # (PRESENT + LATE × 0.65) / WORKING_DAYS × 100
    score_numerator = total_present + (total_late * LATE_PENALTY_WEIGHT)
    overall = min((score_numerator / working_days) * 100, 100) if working_days > 0 else 0

    # ── Attendance % (display) — used on Monthly Present % card ─
    # (PRESENT + LATE) / WORKING_DAYS × 100
    attendance_present = total_present + total_late
    attendance_pct = min(
        (attendance_present / working_days) * 100, 100
    )

    # ── Punctuality — kept for insights display ──────────
    present_days = total_present + total_late
    if present_days > 0:
        punctuality = ((present_days - total_late) / present_days) * 100
        punctuality = max(punctuality, 0)
    else:
        punctuality = 0

    # ── Consistency — kept for insights display ──────────
    consistency = await _compute_consistency(db, employee_id, month, year)

    # ── Work Hours Quality — kept for insights display ───
    work_hours_quality = 40.0
    if monthly.avg_work_hrs and isinstance(monthly.avg_work_hrs, timedelta):
        avg_hours = monthly.avg_work_hrs.total_seconds() / 3600
        if avg_hours >= 8:
            work_hours_quality = 100.0
        elif avg_hours >= 6:
            work_hours_quality = 70.0

    return {
        "overall": round(overall, 1),
        "attendance_pct": round(attendance_pct, 1),
        "punctuality": round(punctuality, 1),
        "consistency": round(consistency, 1),
        "work_hours_quality": round(work_hours_quality, 1),
        "working_days": working_days,
    }


async def _compute_consistency(
    db: AsyncSession,
    employee_id: int,
    month: int,
    year: int,
) -> float:
    """
    Compute consistency score from login time variance.

    - Collects all first_in times for the month
    - Computes standard deviation in minutes
    - Maps to 0-100 score: 0 std dev = 100, 60+ min std dev = 0
    """
    from calendar import monthrange
    first_d = date(year, month, 1)
    last_d = date(year, month, monthrange(year, month)[1])

    result = await db.execute(
        select(AttendanceLog).where(
            AttendanceLog.employee_id == employee_id,
            AttendanceLog.log_date >= first_d,
            AttendanceLog.log_date <= last_d,
        )
    )
    all_logs = result.scalars().all()

    login_minutes = []
    for log in all_logs:
        if (log.first_in is not None
                and log.status not in ("WEEKEND", "HOLIDAY", "ON_LEAVE")):
            # Convert first_in to minutes since midnight
            fi = log.first_in
            if hasattr(fi, 'hour'):
                minutes = fi.hour * 60 + fi.minute
                login_minutes.append(minutes)

    if len(login_minutes) < 2:
        return 100.0  # Not enough data, assume consistent

    std_dev = statistics.stdev(login_minutes)

    # Map: 0 min std dev → 100, 60+ min → 0
    consistency = max(0, 100 - (std_dev / 60) * 100)
    return round(consistency, 1)


async def generate_insights(
    db: AsyncSession,
    employee_id: int,
    month: int,
    year: int,
) -> List[Dict[str, str]]:
    """
    Generate dynamic attendance insights for an employee.

    Returns:
        List of insight dicts with 'type' (info/warning/danger/success)
        and 'message'.
    """
    insights: List[Dict[str, str]] = []

    # Get monthly summary
    result = await db.execute(
        select(AttendanceMonthly).where(
            AttendanceMonthly.employee_id == employee_id,
            AttendanceMonthly.month == month,
            AttendanceMonthly.year == year,
        )
    )
    monthly = result.scalar_one_or_none()

    if not monthly:
        insights.append({
            "type": "info",
            "message": "📊 No attendance data for this month yet.",
        })
        return insights

    # ── Perfect attendance ──────────────────────────────
    half_ok = monthly.total_half_day == 0
    if monthly.total_absent == 0 and monthly.total_late == 0 and half_ok:
        insights.append({
            "type": "success",
            "message": "✅ Perfect attendance this month — no absences or late arrivals!",
        })

    # ── Late warning ────────────────────────────────────
    if monthly.total_late >= 3:
        insights.append({
            "type": "warning",
            "message": f"⚠️ {monthly.total_late} late arrivals this month → Warning threshold reached",
        })
    elif monthly.total_late > 0:
        insights.append({
            "type": "info",
            "message": f"🕐 {monthly.total_late} late arrival(s) this month",
        })

    # ── Absence alert ───────────────────────────────────
    if monthly.total_absent >= 3:
        insights.append({
            "type": "danger",
            "message": f"🚨 {monthly.total_absent} absences this month — requires attention",
        })
    elif monthly.total_absent > 0:
        insights.append({
            "type": "info",
            "message": f"📋 {monthly.total_absent} absence(s) this month",
        })

    # ── Weekly absence check ────────────────────────────
    weekly_absences = await _check_weekly_absences(db, employee_id)
    if weekly_absences >= 2:
        insights.append({
            "type": "danger",
            "message": f"🚨 {weekly_absences} absences this week → Issue flagged",
        })

    # ── Work hours trend ────────────────────────────────
    if monthly.avg_work_hrs:
        avg_td = monthly.avg_work_hrs
        if isinstance(avg_td, timedelta):
            avg_hours = avg_td.total_seconds() / 3600
            if avg_hours >= 9:
                insights.append({
                    "type": "success",
                    "message": f"📈 Strong work hours — averaging {avg_hours:.1f}h/day",
                })
            elif avg_hours < 7.5:
                insights.append({
                    "type": "warning",
                    "message": f"⚠️ Below minimum — averaging {avg_hours:.1f}h/day (min: 8h)",
                })

    # ── Leave usage ─────────────────────────────────────
    if monthly.total_leave > 0:
        insights.append({
            "type": "info",
            "message": f"🏖️ {monthly.total_leave} day(s) on leave this month",
        })

    return insights


async def _check_weekly_absences(
    db: AsyncSession,
    employee_id: int,
) -> int:
    """Count absences in the current ISO week."""
    today = date.today()
    # Monday of current week
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)

    result = await db.execute(
        select(AttendanceLog).where(
            AttendanceLog.employee_id == employee_id,
            AttendanceLog.log_date >= monday,
            AttendanceLog.log_date <= friday,
        )
    )
    all_logs = result.scalars().all()

    return sum(
        1 for log in all_logs
        if monday <= log.log_date <= friday
        and log.status == "ABSENT"
    )
