"""
CRUD operations for the ``attendance_monthly`` table.

Provides an async upsert function that:
1. Resolves ``employee_code`` → ``employee_id`` via the ``employees`` table.
2. Checks provenance: rows with ``data_source == 'MANUAL_CSV'`` are
   **never** overwritten by API data — preserving manual admin corrections.
3. Uses PostgreSQL ``ON CONFLICT (employee_id, month, year) DO UPDATE``
   with a ``WHERE`` guard for the provenance rule.
"""
from __future__ import annotations

import json
import logging
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.monthly_sync import (
    MonthlyAttendanceSyncSchema,
    MonthlySyncResult,
)

logger = logging.getLogger(__name__)


async def resolve_employee_id(
    db: AsyncSession,
    employee_code: str,
) -> Optional[int]:
    """
    Look up the internal ``employees.id`` for a given COSEC user-id.

    Returns:
        The integer PK, or ``None`` if the employee is not registered.
    """
    result = await db.execute(
        text("SELECT id FROM employees WHERE employee_code = :code"),
        {"code": employee_code},
    )
    row = result.fetchone()
    return row[0] if row else None


async def upsert_monthly_record(
    db: AsyncSession,
    record: MonthlyAttendanceSyncSchema,
    source: str = "API",
    skip_manual: bool = True,
) -> str:
    """
    Upsert a single validated monthly attendance record into
    ``attendance_monthly``.

    **Provenance rule:** If ``skip_manual=True`` and the existing DB row
    has ``data_source == 'MANUAL_CSV'``, the row is **not** overwritten.
    This is enforced both in the Python guard and in the SQL
    ``WHERE attendance_monthly.data_source != 'MANUAL_CSV'`` clause for
    defence-in-depth.

    Args:
        db: Active async SQLAlchemy session (caller manages transaction).
        record: Validated ``MonthlyAttendanceSyncSchema`` instance.
        source: Data source tag (default ``"API"``).
        skip_manual: When ``True``, protect ``MANUAL_CSV`` records.

    Returns:
        One of ``"inserted"``, ``"updated"``, or ``"skipped"``.
    """
    # ── Resolve employee_id ────────────────────────────────
    employee_id = await resolve_employee_id(db, record.employee_code)
    if employee_id is None:
        logger.debug(
            "Employee code '%s' not found in DB — skipping monthly record.",
            record.employee_code,
        )
        return "skipped"

    # ── Check existing record provenance ───────────────────
    existing = await db.execute(
        text(
            "SELECT id, data_source FROM attendance_monthly "
            "WHERE employee_id = :eid AND month = :month AND year = :year"
        ),
        {"eid": employee_id, "month": record.month, "year": record.year},
    )
    existing_row = existing.fetchone()

    if existing_row and skip_manual and existing_row[1] == "MANUAL_CSV":
        logger.debug(
            "Skipping employee %s for %02d/%d — protected MANUAL_CSV record.",
            record.employee_code,
            record.month,
            record.year,
        )
        return "skipped"

    # ── Compute interval string for avg_work_hrs ───────────
    avg_work_hrs_str = record.avg_work_hours_interval_str

    # ── Perform upsert ─────────────────────────────────────
    await db.execute(
        text("""
            INSERT INTO attendance_monthly
                (employee_id, month, year,
                 total_present, total_absent, total_late,
                 total_half_day, total_leave,
                 avg_work_hrs, data_source)
            VALUES
                (:eid, :month, :year,
                 :present, :absent, :late,
                 :half_day, :leave,
                 :avg_wh ::interval, :src)
            ON CONFLICT (employee_id, month, year)
            DO UPDATE SET
                total_present  = EXCLUDED.total_present,
                total_absent   = EXCLUDED.total_absent,
                total_late     = EXCLUDED.total_late,
                total_half_day = EXCLUDED.total_half_day,
                total_leave    = EXCLUDED.total_leave,
                avg_work_hrs   = EXCLUDED.avg_work_hrs,
                data_source    = EXCLUDED.data_source,
                updated_at     = NOW()
            WHERE attendance_monthly.data_source != 'MANUAL_CSV'
        """),
        {
            "eid": employee_id,
            "month": record.month,
            "year": record.year,
            "present": record.total_present,
            "absent": record.total_absent,
            "late": record.total_late,
            "half_day": record.total_half_day,
            "leave": record.total_leave,
            "avg_wh": avg_work_hrs_str,
            "src": source,
        },
    )

    if existing_row:
        return "updated"
    return "inserted"


async def sync_monthly_batch(
    db: AsyncSession,
    records: List[MonthlyAttendanceSyncSchema],
    source: str = "API",
) -> MonthlySyncResult:
    """
    Upsert a batch of validated monthly records in a single transaction.

    Args:
        db: Active async SQLAlchemy session.
        records: Pre-validated ``MonthlyAttendanceSyncSchema`` list.
        source: Data source tag.

    Returns:
        ``MonthlySyncResult`` with counts and any error messages.
    """
    result = MonthlySyncResult(
        total_fetched=len(records),
        validated=len(records),
    )

    for record in records:
        try:
            outcome = await upsert_monthly_record(
                db, record, source=source, skip_manual=True
            )
            if outcome == "inserted":
                result.inserted += 1
            elif outcome == "updated":
                result.updated += 1
            else:
                result.skipped += 1
        except Exception as exc:
            result.errors += 1
            msg = (
                f"Upsert failed for {record.employee_code} "
                f"({record.month:02d}/{record.year}): {exc}"
            )
            result.error_messages.append(msg)
            logger.error(msg)

    # Commit the full batch
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error("Transaction commit failed during monthly sync: %s", exc)
        result.errors += 1
        result.error_messages.append(f"Commit failed: {exc}")

    logger.info(
        "Monthly upsert batch complete — "
        "total=%d inserted=%d updated=%d skipped=%d errors=%d",
        result.total_fetched,
        result.inserted,
        result.updated,
        result.skipped,
        result.errors,
    )
    return result
