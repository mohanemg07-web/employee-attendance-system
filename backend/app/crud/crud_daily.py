"""
CRUD operations for the ``attendance_logs`` table — COSEC Daily sync.

Provides an asynchronous upsert pipeline that:

1. Resolves ``employee_code`` → ``employees.id`` for FK linking.
2. Performs ``INSERT ... ON CONFLICT (employee_id, log_date) DO UPDATE``
   with a **critical provenance rule**: rows where
   ``data_source = 'MANUAL_CSV'`` are **never overwritten** by API data
   to preserve manual admin corrections.
3. Stores the raw COSEC payload for auditing.

The upsert approach handles idempotent re-runs: running the sync
for the same date range twice produces the same result.
"""
from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import _is_sqlite
from app.models.attendance import AttendanceLog
from app.schemas.daily_sync import (
    AttendanceStatus,
    DailyAttendanceSyncSchema,
    DailySyncResult,
)

logger = logging.getLogger(__name__)


# ── Code → ID mapping ─────────────────────────────────────

async def _build_code_to_id_map(
    db: AsyncSession,
) -> Dict[str, int]:
    """
    Build a lookup dict mapping ``employee_code → employees.id``
    for all employees currently in the database.
    """
    result = await db.execute(
        text("SELECT employee_code, id FROM employees")
    )
    return {row[0]: row[1] for row in result.fetchall()}


def _daily_is_late(record: DailyAttendanceSyncSchema) -> bool:
    """Match CSV / insight rules: status LATE or first_in after 09:00 IST."""
    if record.status == AttendanceStatus.LATE:
        return True
    fi = record.first_in
    if fi is None:
        return False
    return fi.hour > 9 or (fi.hour == 9 and fi.minute > 0)


async def _upsert_daily_record_sqlite(
    db: AsyncSession,
    record: DailyAttendanceSyncSchema,
    employee_id: int,
) -> str:
    """ORM upsert for SQLite (no ::interval / ::jsonb / xmax)."""
    log_date = record.log_date
    if log_date is None:
        return "skipped"

    res = await db.execute(
        select(AttendanceLog).where(
            AttendanceLog.employee_id == employee_id,
            AttendanceLog.log_date == log_date,
        )
    )
    existing = res.scalar_one_or_none()
    if existing and existing.data_source == "MANUAL_CSV":
        return "skipped"

    is_late = _daily_is_late(record)
    gross = record.gross_work_hrs
    net = record.net_work_hrs
    status = record.status.value
    raw = record.raw_payload

    if existing:
        existing.first_in = record.first_in
        existing.last_out = record.last_out
        existing.gross_work_hrs = gross
        existing.net_work_hrs = net
        existing.status = status
        existing.is_late = is_late
        existing.data_source = "API"
        existing.raw_payload = raw
        return "updated"

    db.add(
        AttendanceLog(
            employee_id=employee_id,
            log_date=log_date,
            first_in=record.first_in,
            last_out=record.last_out,
            gross_work_hrs=gross,
            net_work_hrs=net,
            status=status,
            is_late=is_late,
            data_source="API",
            raw_payload=raw,
        )
    )
    return "inserted"


# ── Single Record Upsert ──────────────────────────────────

async def upsert_daily_record(
    db: AsyncSession,
    record: DailyAttendanceSyncSchema,
    employee_id: int,
) -> str:
    """
    Upsert a single daily attendance record into ``attendance_logs``.

    **Provenance Rule**: If the existing row has
    ``data_source = 'MANUAL_CSV'``, the row is NOT updated.
    Only rows with ``data_source = 'API'`` or entirely new rows
    are written.

    Uses PostgreSQL ``RETURNING xmax`` to distinguish INSERT (xmax=0)
    from UPDATE (xmax>0).

    Args:
        db: Active async session.
        record: Validated ``DailyAttendanceSyncSchema`` instance.
        employee_id: The internal ``employees.id`` FK value.

    Returns:
        ``"inserted"``, ``"updated"``, or ``"skipped"`` (MANUAL_CSV).
    """
    if _is_sqlite:
        return await _upsert_daily_record_sqlite(db, record, employee_id)

    log_date = record.log_date
    first_in = record.first_in
    last_out = record.last_out
    status = record.status.value
    is_late = _daily_is_late(record)
    gross_work_hrs_str = record.gross_work_hrs_interval_str
    net_work_hrs_str = record.net_work_hrs_interval_str

    # Serialise raw_payload as JSON for the JSONB column
    raw_json = None
    if record.raw_payload:
        try:
            raw_json = json.dumps(record.raw_payload, default=str)
        except (TypeError, ValueError):
            raw_json = None

    result = await db.execute(
        text("""
            INSERT INTO attendance_logs
                (employee_id, log_date, first_in, last_out,
                 gross_work_hrs, net_work_hrs, status, is_late,
                 data_source, raw_payload)
            VALUES
                (:emp_id, :log_date, :first_in, :last_out,
                 :gross_hrs::interval, :net_hrs::interval, :status, :is_late,
                 'API', :raw_payload::jsonb)
            ON CONFLICT (employee_id, log_date)
            DO UPDATE SET
                first_in       = EXCLUDED.first_in,
                last_out       = EXCLUDED.last_out,
                gross_work_hrs = EXCLUDED.gross_work_hrs,
                net_work_hrs   = EXCLUDED.net_work_hrs,
                status         = EXCLUDED.status,
                is_late        = EXCLUDED.is_late,
                raw_payload    = EXCLUDED.raw_payload,
                updated_at     = NOW()
            WHERE
                -- CRITICAL: Never overwrite manual corrections
                attendance_logs.data_source != 'MANUAL_CSV'
            RETURNING xmax
        """),
        {
            "emp_id": employee_id,
            "log_date": log_date,
            "first_in": first_in,
            "last_out": last_out,
            "gross_hrs": gross_work_hrs_str,
            "net_hrs": net_work_hrs_str,
            "status": status,
            "is_late": is_late,
            "raw_payload": raw_json,
        },
    )

    row = result.fetchone()

    if row is None:
        # ON CONFLICT matched but the WHERE clause excluded it
        # → row exists with data_source='MANUAL_CSV' → skipped
        return "skipped"

    # xmax = 0 → INSERT, xmax > 0 → UPDATE
    if row[0] == 0:
        return "inserted"
    return "updated"


# ── Batch Upsert ───────────────────────────────────────────

async def upsert_daily_batch(
    db: AsyncSession,
    records: List[DailyAttendanceSyncSchema],
) -> DailySyncResult:
    """
    Upsert a batch of daily attendance records.

    1. Builds employee_code → id lookup.
    2. Iterates records with per-record savepoints.
    3. Commits at the end.

    Args:
        db: Active async session (caller manages outer transaction).
        records: Pre-validated ``DailyAttendanceSyncSchema`` list.

    Returns:
        ``DailySyncResult`` with comprehensive counts.
    """
    result = DailySyncResult(
        total_fetched=len(records),
        validated=len(records),
    )

    # Build employee_code → id mapping
    code_to_id = await _build_code_to_id_map(db)

    skipped_no_employee: List[str] = []

    for record in records:
        emp_id = code_to_id.get(record.employee_code)

        if emp_id is None:
            result.skipped += 1
            skipped_no_employee.append(record.employee_code)
            continue

        if record.log_date is None:
            result.skipped += 1
            result.error_messages.append(
                f"No log_date for employee {record.employee_code}"
            )
            continue

        try:
            # Savepoint per record — a single failure won't abort batch
            async with db.begin_nested():
                outcome = await upsert_daily_record(db, record, emp_id)
                if outcome == "inserted":
                    result.inserted += 1
                elif outcome == "updated":
                    result.updated += 1
                elif outcome == "skipped":
                    result.skipped += 1
        except Exception as exc:
            result.errors += 1
            msg = (
                f"Daily upsert failed for emp={record.employee_code} "
                f"date={record.log_date}: {exc}"
            )
            result.error_messages.append(msg)
            logger.error(msg)

    if skipped_no_employee:
        unique_codes = sorted(set(skipped_no_employee))
        logger.warning(
            "Skipped %d records for %d unknown employee codes: %s",
            len(skipped_no_employee),
            len(unique_codes),
            unique_codes[:20],
        )

    # Final commit
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        msg = f"Daily batch commit failed: {exc}"
        result.error_messages.append(msg)
        logger.error(msg)
        result.errors += 1

    logger.info(
        "Daily attendance upsert complete — "
        "total=%d inserted=%d updated=%d skipped=%d errors=%d",
        result.total_fetched,
        result.inserted,
        result.updated,
        result.skipped,
        result.errors,
    )
    return result
