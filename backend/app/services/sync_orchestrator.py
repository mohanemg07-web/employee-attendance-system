"""
Sync Orchestrator — glue service connecting Matrix COSEC API services
to the database for automated and manual sync operations.

Provides three high-level methods:
    sync_users()     — User Master API → employees table
    sync_daily()     — Daily Attendance API → attendance_logs table
    sync_monthly()   — Monthly Attendance API → attendance_monthly table

Each method:
    1. Creates a SyncLog entry (status=RUNNING)
    2. Fetches from the COSEC API via dedicated services
    3. Validates records through Pydantic schemas
    4. Upserts into the database (protects MANUAL_CSV records)
    5. Updates the SyncLog entry (status=SUCCESS/FAILED)
    6. Invalidates Redis dashboard caches for affected employees
"""
from __future__ import annotations

import json as _json
import logging
import time
from datetime import date, datetime, timedelta
from typing import List, Optional, Set, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.sync_log import SyncLog
from app.services.matrix_sync import (
    user_master_service,
    daily_attendance_service,
    monthly_service,
)

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────

def _months_in_range(
    start: date, end: date,
) -> Set[Tuple[int, int]]:
    """Return the set of (month, year) tuples spanned by a date range."""
    months: Set[Tuple[int, int]] = set()
    cursor = start.replace(day=1)
    while cursor <= end:
        months.add((cursor.month, cursor.year))
        # Advance to next month
        if cursor.month == 12:
            cursor = cursor.replace(year=cursor.year + 1, month=1)
        else:
            cursor = cursor.replace(month=cursor.month + 1)
    return months


async def _invalidate_caches(
    db: AsyncSession,
    affected_employee_ids: List[int],
) -> None:
    """Best-effort Redis cache invalidation after sync."""
    if not affected_employee_ids:
        return
    try:
        from app.services.cache import invalidate_dashboard_caches
        await invalidate_dashboard_caches(db, affected_employee_ids)
        logger.info(
            "Invalidated dashboard caches for %d employees",
            len(affected_employee_ids),
        )
    except Exception as exc:
        logger.warning("Cache invalidation failed (non-fatal): %s", exc)


class SyncOrchestrator:
    """
    Central orchestration service for Matrix COSEC biometric sync.

    Usage::

        orchestrator = SyncOrchestrator()
        result = await orchestrator.sync_daily(
            start_date=date(2026, 5, 10),
            end_date=date(2026, 5, 10),
            triggered_by="MANUAL",
        )
    """

    # ── User Master Sync ──────────────────────────────────

    async def sync_users(
        self,
        triggered_by: str = "SCHEDULER",
    ) -> dict:
        """
        Fetch all active users from COSEC User Master API and
        upsert into the employees table.

        Resolves manager_id hierarchy from reporting-incharge fields.
        """
        t0 = time.monotonic()

        async with AsyncSessionLocal() as db:
            # Create sync log
            sync_log = SyncLog(
                sync_type="USER",
                status="RUNNING",
                triggered_by=triggered_by,
            )
            db.add(sync_log)
            await db.commit()
            await db.refresh(sync_log)
            log_id = sync_log.id

            try:
                # Fetch from API
                raw_records = await user_master_service.fetch_all_users(
                    active_only=True
                )
                logger.info(
                    "User sync: fetched %d raw records from COSEC API",
                    len(raw_records),
                )

                # Validate
                validated = user_master_service.validate_records(raw_records)
                logger.info(
                    "User sync: validated %d / %d records",
                    len(validated), len(raw_records),
                )

                # Upsert into employees table
                inserted = 0
                updated = 0
                skipped = 0
                errors = 0
                error_messages = []
                manager_links = {}  # employee_code → manager_code

                for record in validated:
                    try:
                        email = record.best_email
                        if not email:
                            # Generate placeholder email if none available
                            email = f"{record.employee_code}@biometric.local"

                        # Check if employee exists
                        existing = await db.execute(
                            text(
                                "SELECT id, data_source FROM employees "
                                "WHERE employee_code = :code"
                            ),
                            {"code": record.employee_code},
                        )
                        existing_row = existing.fetchone()

                        if existing_row:
                            # Update existing
                            await db.execute(
                                text("""
                                    UPDATE employees SET
                                        full_name = :name,
                                        department = :dept,
                                        is_active = :active,
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE employee_code = :code
                                """),
                                {
                                    "name": record.full_name,
                                    "dept": record.department_display,
                                    "active": record.is_active,
                                    "code": record.employee_code,
                                },
                            )
                            updated += 1
                        else:
                            # Insert new employee
                            await db.execute(
                                text("""
                                    INSERT INTO employees
                                        (employee_code, email, full_name,
                                         role, department, is_active)
                                    VALUES
                                        (:code, :email, :name,
                                         :role, :dept, :active)
                                """),
                                {
                                    "code": record.employee_code,
                                    "email": email,
                                    "name": record.full_name,
                                    "role": "EMPLOYEE",
                                    "dept": record.department_display,
                                    "active": record.is_active,
                                },
                            )
                            inserted += 1

                        # Track manager links for second pass
                        if record.manager_code:
                            manager_links[record.employee_code] = (
                                record.manager_code
                            )

                    except Exception as exc:
                        errors += 1
                        msg = (
                            f"User upsert failed for "
                            f"{record.employee_code}: {exc}"
                        )
                        error_messages.append(msg)
                        logger.error(msg)

                # Second pass: resolve manager_id links
                manager_links_set = 0
                for emp_code, mgr_code in manager_links.items():
                    try:
                        mgr_result = await db.execute(
                            text(
                                "SELECT id FROM employees "
                                "WHERE employee_code = :code"
                            ),
                            {"code": mgr_code},
                        )
                        mgr_row = mgr_result.fetchone()
                        if mgr_row:
                            await db.execute(
                                text("""
                                    UPDATE employees
                                    SET manager_id = :mgr_id,
                                        role = CASE
                                            WHEN role = 'EMPLOYEE' THEN 'EMPLOYEE'
                                            ELSE role
                                        END
                                    WHERE employee_code = :code
                                """),
                                {
                                    "mgr_id": mgr_row[0],
                                    "code": emp_code,
                                },
                            )
                            manager_links_set += 1

                            # Mark the manager as MANAGER role
                            await db.execute(
                                text("""
                                    UPDATE employees SET role = 'MANAGER'
                                    WHERE id = :mgr_id
                                    AND role = 'EMPLOYEE'
                                """),
                                {"mgr_id": mgr_row[0]},
                            )
                    except Exception as exc:
                        logger.warning(
                            "Manager link failed %s → %s: %s",
                            emp_code, mgr_code, exc,
                        )

                await db.commit()

                # Invalidate all employee/team caches after user sync
                try:
                    from app.services.cache import invalidate_pattern
                    await invalidate_pattern("dashboard:*")
                    logger.info("User sync: invalidated all dashboard caches")
                except Exception as cache_exc:
                    logger.warning(
                        "User sync cache invalidation failed: %s", cache_exc
                    )

                elapsed = round(time.monotonic() - t0)
                # Update sync log
                await db.execute(
                    text("""
                        UPDATE sync_logs SET
                            status = 'SUCCESS',
                            completed_at = CURRENT_TIMESTAMP,
                            duration_seconds = :dur,
                            records_fetched = :fetched,
                            records_inserted = :ins,
                            records_updated = :upd,
                            records_skipped = :skip,
                            records_errors = :err,
                            error_log = :errors,
                            metadata_payload = :meta
                        WHERE id = :id
                    """),
                    {
                        "id": log_id,
                        "dur": elapsed,
                        "fetched": len(raw_records),
                        "ins": inserted,
                        "upd": updated,
                        "skip": skipped,
                        "err": errors,
                        "errors": error_messages[:50] if error_messages else None,
                        "meta": {
                            "validated": len(validated),
                            "manager_links_set": manager_links_set,
                        },
                    },
                )
                await db.commit()

                result = {
                    "sync_log_id": log_id,
                    "status": "SUCCESS",
                    "fetched": len(raw_records),
                    "validated": len(validated),
                    "inserted": inserted,
                    "updated": updated,
                    "skipped": skipped,
                    "errors": errors,
                    "manager_links_set": manager_links_set,
                    "duration_seconds": elapsed,
                }
                logger.info("User sync complete: %s", result)
                return result

            except Exception as exc:
                elapsed = round(time.monotonic() - t0)
                logger.exception("User sync failed: %s", exc)
                try:
                    await db.execute(
                        text("""
                            UPDATE sync_logs SET
                                status = 'FAILED',
                                completed_at = CURRENT_TIMESTAMP,
                                duration_seconds = :dur,
                                error_log = :errors
                            WHERE id = :id
                        """),
                        {
                            "id": log_id,
                            "dur": elapsed,
                            "errors": [str(exc)],
                        },
                    )
                    await db.commit()
                except Exception:
                    pass
                return {
                    "sync_log_id": log_id,
                    "status": "FAILED",
                    "error": str(exc),
                    "duration_seconds": elapsed,
                }

    # ── Daily Attendance Sync ─────────────────────────────

    async def sync_daily(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        triggered_by: str = "SCHEDULER",
    ) -> dict:
        """
        Fetch daily attendance from COSEC API and upsert into
        attendance_logs table.

        Defaults to yesterday if no dates provided.
        Protects MANUAL_CSV records from being overwritten.
        """
        t0 = time.monotonic()
        today = date.today()
        start = start_date or (today - timedelta(days=1))
        end = end_date or (today - timedelta(days=1))

        async with AsyncSessionLocal() as db:
            sync_log = SyncLog(
                sync_type="DAILY",
                status="RUNNING",
                triggered_by=triggered_by,
                metadata_payload={
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                },
            )
            db.add(sync_log)
            await db.commit()
            await db.refresh(sync_log)
            log_id = sync_log.id

            try:
                # Fetch from API
                raw_records = await daily_attendance_service.fetch_daily_attendance(
                    start_date=start,
                    end_date=end,
                )
                logger.info(
                    "Daily sync: fetched %d raw records for %s → %s",
                    len(raw_records), start, end,
                )

                # Validate
                validated = daily_attendance_service.validate_records(
                    raw_records
                )
                logger.info(
                    "Daily sync: validated %d / %d records",
                    len(validated), len(raw_records),
                )

                # Upsert into attendance_logs
                inserted = 0
                updated = 0
                skipped = 0
                errors = 0
                error_messages = []
                affected_employee_ids: List[int] = []

                for record in validated:
                    try:
                        log_date = record.log_date
                        if log_date is None:
                            skipped += 1
                            continue

                        # Resolve employee_id
                        emp_result = await db.execute(
                            text(
                                "SELECT id FROM employees "
                                "WHERE employee_code = :code"
                            ),
                            {"code": record.employee_code},
                        )
                        emp_row = emp_result.fetchone()
                        if not emp_row:
                            skipped += 1
                            continue

                        employee_id = emp_row[0]
                        affected_employee_ids.append(employee_id)

                        # Check existing record provenance
                        existing = await db.execute(
                            text(
                                "SELECT id, data_source FROM attendance_logs "
                                "WHERE employee_id = :eid AND log_date = :ld"
                            ),
                            {"eid": employee_id, "ld": log_date},
                        )
                        existing_row = existing.fetchone()

                        if existing_row and existing_row[1] == "MANUAL_CSV":
                            skipped += 1
                            continue

                        # Prepare values
                        first_in_str = (
                            record.first_in.isoformat()
                            if record.first_in else None
                        )
                        last_out_str = (
                            record.last_out.isoformat()
                            if record.last_out else None
                        )
                        gross_hrs_str = record.gross_work_hrs_interval_str
                        net_hrs_str = record.net_work_hrs_interval_str
                        status_val = record.status.value


                        is_late = status_val == "LATE" or (
                            record.first_in is not None
                            and (
                                record.first_in.hour > 9
                                or (
                                    record.first_in.hour == 9
                                    and record.first_in.minute > 0
                                )
                            )
                        )

                        raw_json = (
                            _json.dumps(record.raw_payload, default=str)
                            if record.raw_payload else None
                        )

                        if existing_row:
                            # Update
                            await db.execute(
                                text("""
                                    UPDATE attendance_logs SET
                                        first_in = :fi,
                                        last_out = :lo,
                                        gross_work_hrs = :gwh,
                                        net_work_hrs = :nwh,
                                        status = :st,
                                        is_late = :late,
                                        data_source = 'API',
                                        raw_payload = :raw,
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE id = :id
                                """),
                                {
                                    "id": existing_row[0],
                                    "fi": first_in_str,
                                    "lo": last_out_str,
                                    "gwh": gross_hrs_str,
                                    "nwh": net_hrs_str,
                                    "st": status_val,
                                    "late": is_late,
                                    "raw": raw_json,
                                },
                            )
                            updated += 1
                        else:
                            # Insert
                            await db.execute(
                                text("""
                                    INSERT INTO attendance_logs
                                        (employee_id, log_date, first_in,
                                         last_out, gross_work_hrs,
                                         net_work_hrs, status, is_late,
                                         data_source, raw_payload)
                                    VALUES
                                        (:eid, :ld, :fi, :lo, :gwh, :nwh,
                                         :st, :late, 'API', :raw)
                                """),
                                {
                                    "eid": employee_id,
                                    "ld": log_date,
                                    "fi": first_in_str,
                                    "lo": last_out_str,
                                    "gwh": gross_hrs_str,
                                    "nwh": net_hrs_str,
                                    "st": status_val,
                                    "late": is_late,
                                    "raw": raw_json,
                                },
                            )
                            inserted += 1

                    except Exception as exc:
                        errors += 1
                        msg = (
                            f"Daily upsert failed for "
                            f"{record.employee_code}/{record.log_date}: {exc}"
                        )
                        error_messages.append(msg)
                        logger.error(msg)

                await db.commit()

                # Deduplicate affected employee IDs
                unique_emp_ids = list(set(affected_employee_ids))

                # Trigger monthly re-aggregation for affected months
                try:
                    from app.services.aggregation import (
                        aggregate_for_affected_months,
                    )
                    affected_months = _months_in_range(start, end)
                    if unique_emp_ids and affected_months:
                        agg_count = await aggregate_for_affected_months(
                            db, unique_emp_ids, affected_months,
                        )
                        await db.commit()
                        logger.info(
                            "Daily sync: re-aggregated %d monthly summaries",
                            agg_count,
                        )
                except Exception as agg_exc:
                    logger.warning(
                        "Post-sync aggregation failed: %s", agg_exc
                    )

                # Invalidate dashboard caches for affected employees
                await _invalidate_caches(db, unique_emp_ids)

                elapsed = round(time.monotonic() - t0)
                await db.execute(
                    text("""
                        UPDATE sync_logs SET
                            status = 'SUCCESS',
                            completed_at = CURRENT_TIMESTAMP,
                            duration_seconds = :dur,
                            records_fetched = :fetched,
                            records_inserted = :ins,
                            records_updated = :upd,
                            records_skipped = :skip,
                            records_errors = :err,
                            error_log = :errors
                        WHERE id = :id
                    """),
                    {
                        "id": log_id,
                        "dur": elapsed,
                        "fetched": len(raw_records),
                        "ins": inserted,
                        "upd": updated,
                        "skip": skipped,
                        "err": errors,
                        "errors": error_messages[:50] if error_messages else None,
                    },
                )
                await db.commit()

                result = {
                    "sync_log_id": log_id,
                    "status": "SUCCESS",
                    "date_range": f"{start} → {end}",
                    "fetched": len(raw_records),
                    "validated": len(validated),
                    "inserted": inserted,
                    "updated": updated,
                    "skipped": skipped,
                    "errors": errors,
                    "duration_seconds": elapsed,
                }
                logger.info("Daily sync complete: %s", result)
                return result

            except Exception as exc:
                elapsed = round(time.monotonic() - t0)
                logger.exception("Daily sync failed: %s", exc)
                try:
                    await db.execute(
                        text("""
                            UPDATE sync_logs SET
                                status = 'FAILED',
                                completed_at = CURRENT_TIMESTAMP,
                                duration_seconds = :dur,
                                error_log = :errors
                            WHERE id = :id
                        """),
                        {"id": log_id, "dur": elapsed, "errors": [str(exc)]},
                    )
                    await db.commit()
                except Exception:
                    pass
                return {
                    "sync_log_id": log_id,
                    "status": "FAILED",
                    "error": str(exc),
                    "duration_seconds": elapsed,
                }

    # ── Monthly Attendance Sync ───────────────────────────

    async def sync_monthly(
        self,
        month: Optional[int] = None,
        year: Optional[int] = None,
        triggered_by: str = "SCHEDULER",
    ) -> dict:
        """
        Fetch monthly attendance summaries from COSEC API and
        upsert into attendance_monthly table.
        """
        t0 = time.monotonic()
        now = datetime.now()
        m = month or now.month
        y = year or now.year

        async with AsyncSessionLocal() as db:
            sync_log = SyncLog(
                sync_type="MONTHLY",
                status="RUNNING",
                triggered_by=triggered_by,
                metadata_payload={"month": m, "year": y},
            )
            db.add(sync_log)
            await db.commit()
            await db.refresh(sync_log)
            log_id = sync_log.id

            try:
                # Fetch from API
                raw_records = await monthly_service.fetch_monthly_attendance(
                    month=m, year=y
                )
                logger.info(
                    "Monthly sync: fetched %d raw records for %02d/%04d",
                    len(raw_records), m, y,
                )

                # Validate
                validated = monthly_service.validate_records(raw_records)
                logger.info(
                    "Monthly sync: validated %d / %d records",
                    len(validated), len(raw_records),
                )

                inserted = 0
                updated = 0
                skipped = 0
                errors = 0
                error_messages = []
                affected_employee_ids: List[int] = []

                for record in validated:
                    try:
                        # Resolve employee_id
                        emp_result = await db.execute(
                            text(
                                "SELECT id FROM employees "
                                "WHERE employee_code = :code"
                            ),
                            {"code": record.employee_code},
                        )
                        emp_row = emp_result.fetchone()
                        if not emp_row:
                            skipped += 1
                            continue

                        employee_id = emp_row[0]
                        affected_employee_ids.append(employee_id)

                        # Check existing
                        existing = await db.execute(
                            text(
                                "SELECT id, data_source "
                                "FROM attendance_monthly "
                                "WHERE employee_id = :eid "
                                "AND month = :m AND year = :y"
                            ),
                            {"eid": employee_id, "m": m, "y": y},
                        )
                        existing_row = existing.fetchone()

                        if existing_row and existing_row[1] == "MANUAL_CSV":
                            skipped += 1
                            continue

                        avg_hrs_str = record.avg_work_hours_interval_str

                        if existing_row:
                            await db.execute(
                                text("""
                                    UPDATE attendance_monthly SET
                                        total_present = :present,
                                        total_absent = :absent,
                                        total_late = :late,
                                        total_half_day = :half_day,
                                        total_leave = :leave,
                                        avg_work_hrs = :avg_hrs,
                                        data_source = 'API',
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE id = :id
                                """),
                                {
                                    "id": existing_row[0],
                                    "present": record.total_present,
                                    "absent": record.total_absent,
                                    "late": record.total_late,
                                    "half_day": record.total_half_day,
                                    "leave": record.total_leave,
                                    "avg_hrs": avg_hrs_str,
                                },
                            )
                            updated += 1
                        else:
                            await db.execute(
                                text("""
                                    INSERT INTO attendance_monthly
                                        (employee_id, month, year,
                                         total_present, total_absent,
                                         total_late, total_half_day,
                                         total_leave, avg_work_hrs,
                                         data_source)
                                    VALUES
                                        (:eid, :m, :y,
                                         :present, :absent,
                                         :late, :half_day,
                                         :leave, :avg_hrs,
                                         'API')
                                """),
                                {
                                    "eid": employee_id,
                                    "m": m,
                                    "y": y,
                                    "present": record.total_present,
                                    "absent": record.total_absent,
                                    "late": record.total_late,
                                    "half_day": record.total_half_day,
                                    "leave": record.total_leave,
                                    "avg_hrs": avg_hrs_str,
                                },
                            )
                            inserted += 1

                    except Exception as exc:
                        errors += 1
                        msg = (
                            f"Monthly upsert failed for "
                            f"{record.employee_code}: {exc}"
                        )
                        error_messages.append(msg)
                        logger.error(msg)

                await db.commit()

                # Invalidate dashboard caches for affected employees
                unique_monthly_ids = list(set(affected_employee_ids))
                await _invalidate_caches(db, unique_monthly_ids)

                elapsed = round(time.monotonic() - t0)
                await db.execute(
                    text("""
                        UPDATE sync_logs SET
                            status = 'SUCCESS',
                            completed_at = CURRENT_TIMESTAMP,
                            duration_seconds = :dur,
                            records_fetched = :fetched,
                            records_inserted = :ins,
                            records_updated = :upd,
                            records_skipped = :skip,
                            records_errors = :err,
                            error_log = :errors
                        WHERE id = :id
                    """),
                    {
                        "id": log_id,
                        "dur": elapsed,
                        "fetched": len(raw_records),
                        "ins": inserted,
                        "upd": updated,
                        "skip": skipped,
                        "err": errors,
                        "errors": error_messages[:50] if error_messages else None,
                    },
                )
                await db.commit()

                result = {
                    "sync_log_id": log_id,
                    "status": "SUCCESS",
                    "period": f"{m:02d}/{y:04d}",
                    "fetched": len(raw_records),
                    "validated": len(validated),
                    "inserted": inserted,
                    "updated": updated,
                    "skipped": skipped,
                    "errors": errors,
                    "duration_seconds": elapsed,
                }
                logger.info("Monthly sync complete: %s", result)
                return result

            except Exception as exc:
                elapsed = round(time.monotonic() - t0)
                logger.exception("Monthly sync failed: %s", exc)
                try:
                    await db.execute(
                        text("""
                            UPDATE sync_logs SET
                                status = 'FAILED',
                                completed_at = CURRENT_TIMESTAMP,
                                duration_seconds = :dur,
                                error_log = :errors
                            WHERE id = :id
                        """),
                        {"id": log_id, "dur": elapsed, "errors": [str(exc)]},
                    )
                    await db.commit()
                except Exception:
                    pass
                return {
                    "sync_log_id": log_id,
                    "status": "FAILED",
                    "error": str(exc),
                    "duration_seconds": elapsed,
                }


# ── Module-level singleton ─────────────────────────────────
sync_orchestrator = SyncOrchestrator()
