"""
Attendance router — daily, monthly, today's live, dashboard, and team views.  # v2

Provides:
- /attendance/daily          → Paginated daily logs for the authenticated user
- /attendance/monthly        → Monthly summary (pre-computed or fallback)
- /attendance/today          → Today's live attendance
- /attendance/me/dashboard   → Unified employee dashboard (today + monthly + score + insights)
- /attendance/team/daily     → Team daily attendance (manager/admin)
- /attendance/team/monthly   → Team monthly summaries (manager/admin)
- /attendance/team/dashboard → Unified team dashboard (manager/admin)
"""
from datetime import date, datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.employee import Employee
from app.models.attendance import AttendanceLog, AttendanceMonthly
from app.services.hierarchy import get_subordinate_ids
from app.utils.security import get_current_user, require_role

router = APIRouter(prefix="/attendance", tags=["Attendance"])


def interval_str(val):
    """Convert timedelta/interval to HH:MM:SS string."""
    if not val:
        return None
    s = int(val.total_seconds())
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def present_equivalent_days(total_present: int, total_half_day: int) -> float:
    """Full-day present rows plus half-day credit (matches score / insights logic)."""
    return round(int(total_present) + 0.5 * int(total_half_day or 0), 1)


def log_dict(log):
    """Serialise an AttendanceLog ORM object to dict."""
    return {
        "id": log.id,
        "log_date": log.log_date.isoformat() if hasattr(log.log_date, 'isoformat') else str(log.log_date),
        "first_in": log.first_in.isoformat() if log.first_in else None,
        "last_out": log.last_out.isoformat() if log.last_out else None,
        "gross_work_hrs": interval_str(log.gross_work_hrs),
        "status": log.status,
        "is_late": getattr(log, 'is_late', False),
        "data_source": log.data_source,
    }


# ── Individual Endpoints ────────────────────────────────

@router.get("/daily")
async def get_daily(
    target_date: Optional[date] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get daily attendance logs for the authenticated user."""
    q = select(AttendanceLog).where(AttendanceLog.employee_id == current_user.id)
    if target_date:
        q = q.where(AttendanceLog.log_date == target_date)
    elif start_date and end_date:
        q = q.where(AttendanceLog.log_date.between(start_date, end_date))
    else:
        q = q.where(AttendanceLog.log_date >= date.today() - timedelta(days=30))
    q = q.order_by(AttendanceLog.log_date.desc())
    result = await db.execute(q)
    return {
        "employee_id": current_user.id,
        "employee_name": current_user.full_name,
        "records": [log_dict(l) for l in result.scalars().all()],
    }


@router.get("/monthly")
async def get_monthly(
    month: int = Query(None, ge=1, le=12),
    year: int = Query(None),
    current_user: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get monthly attendance summary for the authenticated user."""
    m = month or datetime.now().month
    y = year or datetime.now().year

    # Try pre-computed monthly table
    r = await db.execute(
        select(AttendanceMonthly).where(
            AttendanceMonthly.employee_id == current_user.id,
            AttendanceMonthly.month == m,
            AttendanceMonthly.year == y,
        )
    )
    mo = r.scalar_one_or_none()
    if mo:
        return {
            "employee_id": current_user.id,
            "employee_name": current_user.full_name,
            "month": m, "year": y,
            "total_present": mo.total_present,
            "total_present_equivalent": present_equivalent_days(
                mo.total_present, mo.total_half_day
            ),
            "total_absent": mo.total_absent,
            "total_late": mo.total_late,
            "total_half_day": mo.total_half_day,
            "total_leave": mo.total_leave,
            "avg_work_hrs": interval_str(mo.avg_work_hrs),
        }

    # Fallback: compute from daily logs using ORM
    all_logs = await db.execute(
        select(AttendanceLog).where(AttendanceLog.employee_id == current_user.id)
    )
    logs = [l for l in all_logs.scalars().all()
            if l.log_date.month == m and l.log_date.year == y
            and l.status not in ("WEEKEND", "HOLIDAY")]

    total_present = sum(1 for l in logs if l.status in ("PRESENT", "LATE"))
    total_absent = sum(1 for l in logs if l.status == "ABSENT")
    total_late = sum(1 for l in logs if l.status == "LATE" or getattr(l, 'is_late', False))
    total_half_day = sum(1 for l in logs if l.status == "HALF_DAY")
    total_leave = sum(1 for l in logs if l.status == "ON_LEAVE")

    # Compute avg work hours
    work_seconds = []
    for l in logs:
        if l.gross_work_hrs and isinstance(l.gross_work_hrs, timedelta):
            work_seconds.append(l.gross_work_hrs.total_seconds())
    avg_hrs = None
    if work_seconds:
        avg_hrs = interval_str(timedelta(seconds=sum(work_seconds) / len(work_seconds)))

    return {
        "employee_id": current_user.id,
        "employee_name": current_user.full_name,
        "month": m, "year": y,
        "total_present": total_present,
        "total_present_equivalent": present_equivalent_days(
            total_present, total_half_day
        ),
        "total_absent": total_absent,
        "total_late": total_late,
        "total_half_day": total_half_day,
        "total_leave": total_leave,
        "avg_work_hrs": avg_hrs,
    }


@router.get("/today")
async def get_today(
    current_user: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get today's live attendance — DB lookup with COSEC fallback."""
    # Try DB first (most reliable for CSV-uploaded data)
    r = await db.execute(
        select(AttendanceLog).where(
            AttendanceLog.employee_id == current_user.id,
            AttendanceLog.log_date == date.today(),
        )
    )
    log = r.scalar_one_or_none()
    if log:
        return {
            "employee_id": current_user.id,
            "employee_name": current_user.full_name,
            "date": date.today().isoformat(),
            "source": "database",
            "data": {
                "first_in": log.first_in.isoformat() if log.first_in else None,
                "last_out": log.last_out.isoformat() if log.last_out else None,
                "gross_work_hrs": interval_str(log.gross_work_hrs),
                "status": log.status,
                "is_late": getattr(log, 'is_late', False),
            },
        }

    # Try COSEC API as fallback
    try:
        from app.services.matrix_cosec import cosec_service
        live = await cosec_service.get_today_attendance(current_user.employee_code)
        if live:
            return {
                "employee_id": current_user.id,
                "employee_name": current_user.full_name,
                "date": date.today().isoformat(),
                "source": "live_api",
                "data": live,
            }
    except Exception:
        pass  # COSEC not configured, continue

    return {
        "employee_id": current_user.id,
        "employee_name": current_user.full_name,
        "date": date.today().isoformat(),
        "source": "none",
        "data": None,
    }


# ── Heatmap Endpoint (any month/year) ────────────────────

from app.utils.rate_limit import rate_limiter

@router.get("/me/heatmap")
async def get_my_heatmap(
    month: int = Query(None, ge=1, le=12),
    year: int = Query(None),
    current_user: Employee = Depends(rate_limiter),
    db: AsyncSession = Depends(get_db),
):
    """
    Return attendance logs for a specific month/year for heatmap rendering.
    """
    from calendar import monthrange

    m = month or datetime.now().month
    y = year or datetime.now().year
    first_day = date(y, m, 1)
    last_day = date(y, m, monthrange(y, m)[1])

    result = await db.execute(
        select(AttendanceLog).where(
            AttendanceLog.employee_id == current_user.id,
            AttendanceLog.log_date >= first_day,
            AttendanceLog.log_date <= last_day,
        ).order_by(AttendanceLog.log_date)
    )
    logs = [log_dict(l) for l in result.scalars().all()]

    return {
        "month": m,
        "year": y,
        "logs": logs,
    }


# ── Work Hours Trend (selectable range) ──────────────────

def _interval_to_hours(val):
    """Convert timedelta or HH:MM:SS string to decimal hours."""
    if val is None:
        return 0.0
    if hasattr(val, "total_seconds"):
        return round(val.total_seconds() / 3600, 2)
    s = str(val)
    parts = s.split(":")
    if len(parts) >= 2:
        try:
            return round(int(parts[0]) + int(parts[1]) / 60, 2)
        except (ValueError, TypeError):
            pass
    return 0.0


@router.get("/me/work-hours-trend")
async def get_work_hours_trend(
    range: str = Query("30d"),
    current_user: Employee = Depends(rate_limiter),
    db: AsyncSession = Depends(get_db),
):
    """
    Return work hours trend data for the selected range.

    Short ranges (7d, 14d, 30d) → daily points.
    Long ranges (1y, 2y, 3y, all) → monthly aggregated points.
    """
    from calendar import monthrange
    from collections import defaultdict

    today = date.today()
    RANGE_DAYS = {
        "7d": 7, "14d": 14, "30d": 30,
        "1y": 365, "2y": 730, "3y": 1095, "all": 3650,
    }

    days_back = RANGE_DAYS.get(range, 30)
    start_date = today - timedelta(days=days_back)
    is_long = range in ("1y", "2y", "3y", "all")

    result = await db.execute(
        select(AttendanceLog).where(
            AttendanceLog.employee_id == current_user.id,
            AttendanceLog.log_date >= start_date,
            AttendanceLog.log_date <= today,
        ).order_by(AttendanceLog.log_date)
    )
    logs = result.scalars().all()

    if is_long:
        # Monthly aggregation
        monthly = defaultdict(lambda: {"total_hours": 0.0, "count": 0})
        for log in logs:
            key = f"{log.log_date.year}-{log.log_date.month:02d}"
            hrs = _interval_to_hours(log.gross_work_hrs)
            if hrs > 0:
                monthly[key]["total_hours"] += hrs
                monthly[key]["count"] += 1
        
        points = []
        for key in sorted(monthly.keys()):
            y_val, m_val = key.split("-")
            from calendar import month_abbr
            label = f"{month_abbr[int(m_val)]} {y_val}"
            avg_hrs = round(monthly[key]["total_hours"] / monthly[key]["count"], 1) if monthly[key]["count"] > 0 else 0
            points.append({
                "date": label,
                "hours": avg_hrs,
                "total_hours": round(monthly[key]["total_hours"], 1),
                "days_worked": monthly[key]["count"],
            })
    else:
        # Daily points
        points = []
        for log in logs:
            hrs = _interval_to_hours(log.gross_work_hrs)
            if hrs > 0:
                from calendar import month_abbr
                label = f"{month_abbr[log.log_date.month]} {log.log_date.day:02d}"
                points.append({
                    "date": label,
                    "hours": hrs,
                })

    return {
        "range": range,
        "points": points,
        "aggregation": "monthly" if is_long else "daily",
    }


# ── Unified Employee Dashboard ──────────────────────────

@router.get("/me/dashboard")
async def get_my_dashboard(
    month: int = Query(None, ge=1, le=12),
    year: int = Query(None),
    current_user: Employee = Depends(rate_limiter),
    db: AsyncSession = Depends(get_db),
):
    """
    Unified employee dashboard — single API call for the entire view.

    Returns today's status, monthly summary, attendance score, and insights.
    """
    m = month or datetime.now().month
    y = year or datetime.now().year

    # ── Check Cache ───────────────────────────────────
    try:
        from app.services.cache import get_cache, set_cache
        cache_key = f"dashboard:me:{current_user.id}:{m}:{y}"
        cached_data = await get_cache(cache_key)
        if cached_data:
            return cached_data
    except Exception:
        pass # If cache fails, fall back to db computation

    # ── Today ─────────────────────────────────────────
    today_result = await db.execute(
        select(AttendanceLog).where(
            AttendanceLog.employee_id == current_user.id,
            AttendanceLog.log_date == date.today(),
        )
    )
    today_log = today_result.scalar_one_or_none()

    today_data = None
    if today_log:
        today_data = {
            "first_in": today_log.first_in.isoformat() if today_log.first_in else None,
            "last_out": today_log.last_out.isoformat() if today_log.last_out else None,
            "work_hours": interval_str(today_log.gross_work_hrs),
            "status": today_log.status,
            "is_late": getattr(today_log, 'is_late', False),
        }

    # ── Monthly summary ───────────────────────────────
    monthly_result = await db.execute(
        select(AttendanceMonthly).where(
            AttendanceMonthly.employee_id == current_user.id,
            AttendanceMonthly.month == m,
            AttendanceMonthly.year == y,
        )
    )
    monthly = monthly_result.scalar_one_or_none()

    # Dynamic working days: Mon-Sat up to today, excluding Sundays only
    from app.services.insights import _working_days_in_month
    working_days = _working_days_in_month(m, y)

    if monthly:
        total_present = monthly.total_present or 0  # COUNT(status='PRESENT')
        total_late = monthly.total_late or 0         # COUNT(status='LATE')
        total_absent = monthly.total_absent or 0     # COUNT(status='ABSENT')
        total_half_day = monthly.total_half_day or 0
        total_leave = monthly.total_leave or 0       # COUNT(status='ON_LEAVE')

        # Days Present = PRESENT + LATE (business rule)
        days_present = total_present + total_late
        # Monthly Present % = (PRESENT + LATE) / WORKING_DAYS × 100
        present_pct = round((days_present / working_days) * 100, 1) if working_days > 0 else 0
        # Total Working Days = WORKING_DAYS (no deductions)
        total_days = working_days

        monthly_data = {
            "total_present": days_present,       # "Days Present" = PRESENT + LATE
            "total_present_equivalent": present_equivalent_days(
                monthly.total_present, total_half_day
            ),
            "total_absent": total_absent,
            "total_late": total_late,
            "total_half_day": total_half_day,
            "total_leave": total_leave,
            "avg_work_hrs": interval_str(monthly.avg_work_hrs),
            "working_days": working_days,
            "total_days": total_days,
            "present_percent": present_pct,
            "present_percent_trend": 0,
        }
    else:
        # Fallback computation from daily logs (with date filter)
        from calendar import monthrange
        from datetime import date as dt_date
        first_day = dt_date(y, m, 1)
        last_day = dt_date(y, m, monthrange(y, m)[1])
        all_logs = await db.execute(
            select(AttendanceLog).where(
                AttendanceLog.employee_id == current_user.id,
                AttendanceLog.log_date >= first_day,
                AttendanceLog.log_date <= last_day,
            )
        )
        logs = [l for l in all_logs.scalars().all()
                if l.status not in ("WEEKEND", "HOLIDAY")]

        tp = sum(1 for l in logs if l.status == "PRESENT")
        tl = sum(1 for l in logs if l.status == "LATE")
        thd = sum(1 for l in logs if l.status == "HALF_DAY")
        t_leave = sum(1 for l in logs if l.status == "ON_LEAVE")

        # Days Present = PRESENT + LATE
        days_present = tp + tl
        # Monthly Present % = (PRESENT + LATE) / WORKING_DAYS × 100
        present_pct = round((days_present / working_days) * 100, 1) if working_days > 0 else 0
        # Total Working Days = WORKING_DAYS (no deductions)
        total_days = working_days

        monthly_data = {
            "total_present": days_present,       # "Days Present" = PRESENT + LATE
            "total_present_equivalent": present_equivalent_days(tp, thd),
            "total_absent": sum(1 for l in logs if l.status == "ABSENT"),
            "total_late": tl,
            "total_half_day": thd,
            "total_leave": t_leave,
            "avg_work_hrs": None,
            "working_days": working_days,
            "total_days": total_days,
            "present_percent": present_pct,
            "present_percent_trend": 0,
        }

    # ── Score ─────────────────────────────────────────
    from app.services.insights import compute_score, generate_insights

    score = await compute_score(db, current_user.id, m, y)
    insights = await generate_insights(db, current_user.id, m, y)

    # ── Recent Logs (last 30 days) ────────────────────
    recent_result = await db.execute(
        select(AttendanceLog).where(
            AttendanceLog.employee_id == current_user.id,
            AttendanceLog.log_date >= date.today() - timedelta(days=30),
        ).order_by(AttendanceLog.log_date.desc())
    )
    recent_logs_data = [log_dict(l) for l in recent_result.scalars().all()]

    response_data = {
        "employee_id": current_user.id,
        "employee_name": current_user.full_name,
        "month": m,
        "year": y,
        "today": today_data,
        "monthly": monthly_data,
        "score": score,
        "insights": insights,
        "recent_logs": recent_logs_data,
    }

    try:
        from app.services.cache import set_cache
        # cache_key was defined above
        await set_cache(f"dashboard:me:{current_user.id}:{m}:{y}", response_data, ttl_seconds=300)
    except Exception:
        pass

    return response_data


# ── Team Endpoints (Manager/Admin) — ORM-based for cross-DB compat ──

@router.get("/team/daily")
async def get_team_daily(
    target_date: date = Query(None),
    current_user: Employee = Depends(require_role("MANAGER", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Get daily attendance for all subordinates (CTE-scoped)."""
    d = target_date or date.today()
    sub_ids = await get_subordinate_ids(db, current_user.id, include_self=False)
    if not sub_ids:
        return {"date": d.isoformat(), "records": [], "summary": {}}

    # Use ORM with IN clause (works on both Postgres and SQLite)
    result = await db.execute(
        select(AttendanceLog, Employee)
        .join(Employee, Employee.id == AttendanceLog.employee_id)
        .where(
            AttendanceLog.employee_id.in_(sub_ids),
            AttendanceLog.log_date == d,
        )
        .order_by(Employee.full_name)
    )
    rows = result.all()

    records = []
    for log, emp in rows:
        records.append({
            "id": log.id,
            "employee_id": log.employee_id,
            "employee_name": emp.full_name,
            "employee_code": emp.employee_code,
            "log_date": log.log_date.isoformat() if hasattr(log.log_date, 'isoformat') else str(log.log_date),
            "first_in": log.first_in.isoformat() if log.first_in else None,
            "last_out": log.last_out.isoformat() if log.last_out else None,
            "gross_work_hrs": interval_str(log.gross_work_hrs),
            "status": log.status,
            "is_late": getattr(log, 'is_late', False),
            "data_source": log.data_source,
        })

    total = len(sub_ids)
    present = sum(1 for r in records if r["status"] in ("PRESENT", "LATE"))
    absent = sum(1 for r in records if r["status"] == "ABSENT")
    late = sum(1 for r in records if r["status"] == "LATE" or r.get("is_late", False))

    return {
        "date": d.isoformat(),
        "records": records,
        "summary": {
            "total_employees": total,
            "total_present": present,
            "total_absent": absent,
            "total_late": late,
            "attendance_rate": round((present / total) * 100, 1) if total else 0,
        },
    }


@router.get("/team/monthly")
async def get_team_monthly(
    month: int = Query(None, ge=1, le=12),
    year: int = Query(None),
    current_user: Employee = Depends(require_role("MANAGER", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Get monthly attendance summaries for all subordinates."""
    m = month or datetime.now().month
    y = year or datetime.now().year

    sub_ids = await get_subordinate_ids(db, current_user.id, include_self=False)
    if not sub_ids:
        return {"month": m, "year": y, "records": []}

    # Fetch all employees and their attendance using ORM
    emp_result = await db.execute(
        select(Employee).where(Employee.id.in_(sub_ids)).order_by(Employee.full_name)
    )
    employees = emp_result.scalars().all()

    # Date-range filter to avoid loading entire attendance history
    from calendar import monthrange
    from datetime import date as dt_date
    first_day = dt_date(y, m, 1)
    last_day = dt_date(y, m, monthrange(y, m)[1])

    log_result = await db.execute(
        select(AttendanceLog).where(
            AttendanceLog.employee_id.in_(sub_ids),
            AttendanceLog.log_date >= first_day,
            AttendanceLog.log_date <= last_day,
        )
    )
    all_logs = log_result.scalars().all()

    # Filter and aggregate in Python (cross-DB compatible)
    records = []
    for emp in employees:
        emp_logs = [l for l in all_logs
                    if l.employee_id == emp.id
                    and l.log_date.month == m
                    and l.log_date.year == y
                    and l.status not in ("WEEKEND", "HOLIDAY")]
        records.append({
            "employee_id": emp.id,
            "employee_name": emp.full_name,
            "employee_code": emp.employee_code,
            "department": emp.department,
            "total_present": sum(1 for l in emp_logs if l.status in ("PRESENT", "LATE")),
            "total_absent": sum(1 for l in emp_logs if l.status == "ABSENT"),
            "total_late": sum(1 for l in emp_logs if l.status == "LATE" or getattr(l, 'is_late', False)),
            "total_half_day": sum(1 for l in emp_logs if l.status == "HALF_DAY"),
            "total_leave": sum(1 for l in emp_logs if l.status == "ON_LEAVE"),
        })

    return {"month": m, "year": y, "records": records}


# ── Unified Team Dashboard ──────────────────────────────

@router.get("/team/dashboard", dependencies=[Depends(rate_limiter)])
async def get_team_dashboard(
    target_date: date = Query(None),
    month: int = Query(None, ge=1, le=12),
    year: int = Query(None),
    current_user: Employee = Depends(require_role("MANAGER", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """
    Unified team dashboard — single API call for the manager view.

    Returns team size, today's summary, per-member status, monthly stats,
    trend_data (daily attendance rates), top_performers, and risk_alerts.
    """
    import time as _time
    t0 = _time.time()

    d = target_date or date.today()
    m = month or datetime.now().month
    y = year or datetime.now().year

    # ── Check Cache ───────────────────────────────────
    try:
        from app.services.cache import get_cache
        cache_key = f"dashboard:team:{current_user.id}:{m}:{y}"
        cached_data = await get_cache(cache_key)
        if cached_data:
            return cached_data
    except Exception:
        pass

    sub_ids = await get_subordinate_ids(db, current_user.id, include_self=False)
    if not sub_ids:
        return {
            "team_size": 0,
            "date": d.isoformat(),
            "total_present": 0,
            "total_absent": 0,
            "total_late": 0,
            "attendance_rate": 0,
            "members": [],
            "trend_data": [],
            "top_performers": [],
            "risk_alerts": {"low_attendance": 0, "frequent_late": 0, "missing_logs": 0},
        }

    # ── Fetch employees (lightweight — no eager loads) ─
    emp_result = await db.execute(
        select(Employee).where(Employee.id.in_(sub_ids))
    )
    emp_map = {e.id: e for e in emp_result.scalars().all()}

    # ── Today's data (single query) ───────────────────
    result = await db.execute(
        select(AttendanceLog, Employee)
        .join(Employee, Employee.id == AttendanceLog.employee_id)
        .where(
            AttendanceLog.employee_id.in_(sub_ids),
            AttendanceLog.log_date == d,
        )
        .order_by(Employee.full_name)
    )
    rows = result.all()

    # ── Monthly data (single query, merged) ───────────
    from calendar import monthrange
    from datetime import date as dt_date
    first_day = dt_date(y, m, 1)
    last_day = dt_date(y, m, monthrange(y, m)[1])

    monthly_result = await db.execute(
        select(AttendanceLog).where(
            AttendanceLog.employee_id.in_(sub_ids),
            AttendanceLog.log_date >= first_day,
            AttendanceLog.log_date <= last_day,
            AttendanceLog.status.notin_(["WEEKEND", "HOLIDAY"]),
        )
    )
    monthly_logs = monthly_result.scalars().all()

    # Build per-employee monthly aggregates
    from collections import defaultdict
    monthly_agg = defaultdict(lambda: {"present": 0, "absent": 0, "late": 0, "half_day": 0, "leave": 0})
    for log in monthly_logs:
        a = monthly_agg[log.employee_id]
        if log.status == "PRESENT":
            a["present"] += 1
        elif log.status == "LATE":
            a["late"] += 1
        elif log.status == "ABSENT":
            a["absent"] += 1
        elif log.status == "HALF_DAY":
            a["half_day"] += 1
        elif log.status == "ON_LEAVE":
            a["leave"] += 1
        # Also flag late for PRESENT logs that arrived after cutoff
        if log.status != "LATE" and getattr(log, 'is_late', False):
            a["late"] += 1

    # Build today-log lookup: employee_id → (log, emp)
    today_lookup = {}
    for log, emp in rows:
        today_lookup[emp.id] = (log, emp)

    # ── Per-member score computation ──────────────────
    from app.services.insights import compute_score, _working_days_in_month
    working_days = _working_days_in_month(m, y)

    members = []
    for emp_id in sub_ids:
        emp = emp_map.get(emp_id)
        if not emp:
            continue

        agg = monthly_agg.get(emp_id, {})
        mp = agg.get("present", 0)
        ml = agg.get("late", 0)

        # Attendance score per member: (PRESENT + LATE*0.65) / WORKING_DAYS * 100
        member_score = round(((mp + ml * 0.65) / working_days) * 100, 1) if working_days > 0 else 0

        entry = {
            "employee_id": emp.id,
            "employee_name": emp.full_name,
            "employee_code": emp.employee_code,
            "department": emp.department,
            # Monthly stats
            "present": mp,
            "absent": agg.get("absent", 0),
            "late": ml,
            "half_day": agg.get("half_day", 0),
            "leave": agg.get("leave", 0),
            "working_days": working_days,
            "score": member_score,
        }

        # Overlay today's log data if available
        if emp_id in today_lookup:
            log, _ = today_lookup[emp_id]
            entry["status"] = log.status
            entry["first_in"] = log.first_in.isoformat() if log.first_in else None
            entry["last_out"] = log.last_out.isoformat() if log.last_out else None
            entry["work_hours"] = interval_str(log.gross_work_hrs)
            entry["is_late"] = getattr(log, 'is_late', False)
        else:
            entry["status"] = "NO_LOG"
            entry["first_in"] = None
            entry["last_out"] = None
            entry["work_hours"] = None
            entry["is_late"] = False

        members.append(entry)

    # Sort by name for consistent ordering
    members.sort(key=lambda x: x.get("employee_name", ""))

    team_size = len(sub_ids)

    # ── Today's summary (from today's logs only) ──────
    today_present = sum(1 for _, (log, _) in today_lookup.items() if log.status == "PRESENT")
    today_late = sum(1 for _, (log, _) in today_lookup.items() if log.status == "LATE")
    today_absent = sum(1 for _, (log, _) in today_lookup.items() if log.status == "ABSENT")
    today_on_leave = sum(1 for _, (log, _) in today_lookup.items() if log.status == "ON_LEAVE")
    # Attendance rate: (PRESENT + LATE) / team_size * 100
    today_attendance_rate = round(((today_present + today_late) / team_size) * 100, 1) if team_size else 0

    today_summary = {
        "team_members": team_size,
        "team_members_present": today_present + today_late,  # PRESENT + LATE = attended
        "present": today_present,
        "absent": today_absent,
        "late": today_late,
        "on_leave": today_on_leave,
        "attendance_rate": today_attendance_rate,
    }

    # ── Trend Data (daily attendance rates for chart) ──
    trend_data = _compute_trend_data(monthly_logs, sub_ids, first_day, last_day)

    # ── Top Performers ────────────────────────────────
    top_performers = _compute_top_performers(monthly_agg, emp_map, first_day, y, m)

    # ── Risk Alerts ───────────────────────────────────
    risk_alerts = _compute_risk_alerts(monthly_agg, sub_ids, first_day, y, m, emp_map=emp_map, today_lookup=today_lookup)

    # ── On-demand aggregation if attendance_monthly is empty ─
    try:
        from app.services.aggregation import aggregate_for_affected_months
        monthly_check = await db.execute(
            select(func.count()).select_from(AttendanceMonthly).where(
                AttendanceMonthly.employee_id.in_(sub_ids),
                AttendanceMonthly.month == m,
                AttendanceMonthly.year == y,
            )
        )
        monthly_count = monthly_check.scalar() or 0
        if monthly_count == 0 and len(monthly_logs) > 0:
            import logging as _log
            _log.getLogger(__name__).info(
                "attendance_monthly empty for team — triggering on-demand aggregation"
            )
            await aggregate_for_affected_months(
                db, list(sub_ids), {(m, y)}
            )
            await db.commit()
    except Exception as agg_err:
        import logging as _log
        _log.getLogger(__name__).warning("On-demand aggregation failed: %s", agg_err)

    import logging as _log
    _log.getLogger(__name__).info(
        "Team dashboard for user=%d: %d members, %.2fs",
        current_user.id, team_size, _time.time() - t0,
    )

    response_data = {
        "team_size": team_size,
        "date": d.isoformat(),
        "month": m,
        "year": y,
        "today_summary": today_summary,
        "total_present": today_present,
        "total_absent": today_absent,
        "total_late": today_late,
        "attendance_rate": today_attendance_rate,
        "members": members,
        "trend_data": trend_data,
        "top_performers": top_performers,
        "risk_alerts": risk_alerts,
    }

    try:
        from app.services.cache import set_cache
        await set_cache(f"dashboard:team:{current_user.id}:{m}:{y}", response_data, ttl_seconds=300)
    except Exception:
        pass

    return response_data


# ── Team Attendance Trend (selectable range) ─────────────

@router.get("/team/attendance-trend")
async def get_team_attendance_trend(
    range: str = Query("30d"),
    current_user: Employee = Depends(require_role("MANAGER", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """
    Return team attendance trend data for a selected range.

    Short ranges (7d–180d) → daily points.
    Long ranges (1y, 2y, 3y, all) → monthly aggregated points.
    """
    from collections import defaultdict
    from calendar import month_abbr

    sub_ids = await get_subordinate_ids(db, current_user.id, include_self=False)
    team_size = len(sub_ids)
    if team_size == 0:
        return {"range": range, "points": [], "aggregation": "daily", "team_size": 0}

    today = date.today()
    RANGE_DAYS = {
        "7d": 7, "14d": 14, "30d": 30, "60d": 60,
        "120d": 120, "180d": 180,
        "1y": 365, "2y": 730, "3y": 1095, "all": 3650,
    }
    days_back = RANGE_DAYS.get(range, 30)
    start_date = today - timedelta(days=days_back)
    is_long = range in ("1y", "2y", "3y", "all")

    result = await db.execute(
        select(AttendanceLog).where(
            AttendanceLog.employee_id.in_(sub_ids),
            AttendanceLog.log_date >= start_date,
            AttendanceLog.log_date <= today,
        ).order_by(AttendanceLog.log_date)
    )
    logs = result.scalars().all()

    if is_long:
        # Monthly aggregation
        monthly = defaultdict(lambda: {"present": 0, "total_days": set()})
        for log in logs:
            key = f"{log.log_date.year}-{log.log_date.month:02d}"
            monthly[key]["total_days"].add(log.log_date)
            if log.status in ("PRESENT", "LATE"):
                monthly[key]["present"] += 1

        points = []
        for key in sorted(monthly.keys()):
            y_val, m_val = key.split("-")
            label = f"{month_abbr[int(m_val)]} {y_val}"
            bucket = monthly[key]
            num_days = len(bucket["total_days"])
            # avg daily attendance % across the month
            avg_pct = round((bucket["present"] / (num_days * team_size)) * 100, 1) if num_days > 0 else 0
            points.append({
                "date": label,
                "attendancePct": min(avg_pct, 100),
            })
    else:
        # Daily aggregation
        daily = defaultdict(lambda: {"present": 0})
        for log in logs:
            if log.status in ("PRESENT", "LATE"):
                daily[log.log_date]["present"] += 1

        points = []
        current = start_date
        while current <= today:
            if current.weekday() < 6:  # Skip Sundays (weekday 6)
                counts = daily.get(current, {"present": 0})
                pct = round((counts["present"] / team_size) * 100, 1)
                points.append({
                    "date": f"{month_abbr[current.month]} {current.day:02d}",
                    "attendancePct": min(pct, 100),
                })
            current += timedelta(days=1)

    return {
        "range": range,
        "points": points,
        "aggregation": "monthly" if is_long else "daily",
        "team_size": team_size,
    }


def _compute_trend_data(monthly_logs, sub_ids, first_day, last_day):
    """
    Compute daily attendance trend from monthly logs.

    Returns a list of dicts with date_label, attendance_pct, present_pct.
    Aggregates in pure Python from already-loaded logs (no extra DB query).
    """
    from collections import defaultdict
    from datetime import timedelta as td

    team_size = len(sub_ids)
    if team_size == 0:
        return []

    # Group logs by date
    daily_counts = defaultdict(lambda: {"present": 0, "absent": 0, "late": 0, "total": 0})
    for log in monthly_logs:
        day = daily_counts[log.log_date]
        day["total"] += 1
        if log.status in ("PRESENT", "LATE"):
            day["present"] += 1
        if log.status == "ABSENT":
            day["absent"] += 1
        if log.status == "LATE" or getattr(log, 'is_late', False):
            day["late"] += 1

    # Build trend list sorted by date
    trend = []
    current = first_day
    today = date.today()
    while current <= last_day and current <= today:
        if current.weekday() < 6:  # Skip Sundays
            counts = daily_counts.get(current, {"present": 0, "absent": 0, "late": 0, "total": 0})
            present = counts["present"]
            total_logged = counts["total"]
            attendance_pct = round((present / team_size) * 100, 1) if team_size else 0
            present_pct = round((present / total_logged) * 100, 1) if total_logged else 0
            trend.append({
                "date_label": current.strftime("%b %d"),
                "date": current.isoformat(),
                "attendance_pct": attendance_pct,
                "present_pct": present_pct,
                "present": present,
                "absent": counts["absent"],
                "late": counts["late"],
            })
        current += td(days=1)

    return trend


def _compute_top_performers(monthly_agg, emp_map, first_day, year, month):
    """
    Compute top 5 performers based on attendance rate.

    Uses monthly_agg (per-employee aggregates) already computed.
    """
    from app.services.insights import _working_days_in_month

    working_days = _working_days_in_month(month, year)
    if working_days == 0:
        return []

    scored = []
    for emp_id, agg in monthly_agg.items():
        emp = emp_map.get(emp_id)
        if not emp:
            continue
        present = agg["present"]
        late = agg["late"]
        half_day = agg["half_day"]
        # Days attended = PRESENT + LATE (business rule)
        days_attended = present + late
        present_eq = days_attended + 0.5 * half_day
        attendance_pct = min((present_eq / working_days) * 100, 100)

        # Punctuality factor
        if present_eq > 0:
            punctuality = max(((present_eq - agg["late"]) / present_eq) * 100, 0)
        else:
            punctuality = 0

        score = round(0.6 * attendance_pct + 0.4 * punctuality, 1)
        scored.append({
            "employee_id": emp_id,
            "name": emp.full_name,
            "department": emp.department,
            "score": score,
            "present": present,
            "absent": agg["absent"],
            "late": agg["late"],
            "attendance_pct": round(attendance_pct, 1),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:5]


def _compute_risk_alerts(monthly_agg, sub_ids, first_day, year, month, emp_map=None, today_lookup=None):
    """
    Compute risk alerts with full employee lists.

    - low_attendance: employees with <75% attendance
    - frequent_late: employees with >=3 late days
    - missing_logs: employees with NO_LOG today (no log entry for today)
    """
    from app.services.insights import _working_days_in_month

    working_days = _working_days_in_month(month, year)
    emp_map = emp_map or {}
    today_lookup = today_lookup or {}

    logged_ids = set(monthly_agg.keys())
    missing_ids = set(sub_ids) - logged_ids

    low_attendance_list = []
    frequent_late_list = []

    for emp_id, agg in monthly_agg.items():
        emp = emp_map.get(emp_id)
        emp_name = emp.full_name if emp else f"Employee #{emp_id}"
        emp_dept = emp.department if emp else "—"

        present_count = agg["present"]
        late_count = agg["late"]
        absent_count = agg["absent"]
        half_day_count = agg["half_day"]

        # Days attended = PRESENT + LATE + 0.5*HALF_DAY
        present_eq = present_count + late_count + 0.5 * half_day_count
        pct = round((present_eq / working_days) * 100, 1) if working_days > 0 else 0

        if working_days > 0 and pct < 75:
            low_attendance_list.append({
                "employee_id": emp_id,
                "employee_name": emp_name,
                "department": emp_dept,
                "attendance_pct": pct,
                "present": present_count,
                "late": late_count,
                "absent": absent_count,
            })

        if late_count >= 3:
            frequent_late_list.append({
                "employee_id": emp_id,
                "employee_name": emp_name,
                "department": emp_dept,
                "late_count": late_count,
            })

    # Missing logs: employees with no today-log OR no monthly data
    missing_log_list = []
    # Employees with no log at all today
    for emp_id in sub_ids:
        if emp_id not in today_lookup:
            emp = emp_map.get(emp_id)
            missing_log_list.append({
                "employee_id": emp_id,
                "employee_name": emp.full_name if emp else f"Employee #{emp_id}",
                "department": emp.department if emp else "—",
                "status": "NO_LOG",
            })

    # Sort lists for consistency
    low_attendance_list.sort(key=lambda x: x["attendance_pct"])
    frequent_late_list.sort(key=lambda x: -x["late_count"])
    missing_log_list.sort(key=lambda x: x["employee_name"])

    return {
        "low_attendance": len(low_attendance_list),
        "frequent_late": len(frequent_late_list),
        "missing_logs": len(missing_log_list),
        "low_attendance_employees": low_attendance_list,
        "frequent_late_employees": frequent_late_list,
        "missing_logs_employees": missing_log_list,
    }


# ── Admin: Manual Aggregation Trigger ───────────────────

@router.post("/admin/aggregate")
async def trigger_aggregation(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(...),
    current_user: Employee = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """
    Admin endpoint to manually trigger monthly aggregation.

    Re-aggregates all employees for the specified month/year.
    """
    from app.services.aggregation import aggregate_monthly_for_all
    count = await aggregate_monthly_for_all(db, month, year)
    return {
        "status": "success",
        "month": month,
        "year": year,
        "employees_aggregated": count,
    }
