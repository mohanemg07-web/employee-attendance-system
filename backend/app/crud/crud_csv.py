"""
CRUD operations for CSV-uploaded attendance data.

Uses PostgreSQL bulk upsert (INSERT ... ON CONFLICT UPDATE) for
maximum performance. Falls back to ORM for SQLite dev mode.

Every row gets ``data_source = 'MANUAL_CSV'``, overwriting any
existing API-sourced records for the same employee + date.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Set, Tuple

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.attendance import AttendanceLog
from app.schemas.csv_sync import (
    CSVAttendanceRowSchema,
    CSVUploadResult,
)

logger = logging.getLogger(__name__)

_NON_WORKING = {"HOLIDAY", "WEEKEND", "ABSENT", "ON_LEAVE"}


async def _build_employee_maps(
    db: AsyncSession,
) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Build employee_code → id and email → id lookups."""
    result = await db.execute(
        select(Employee.employee_code, Employee.email, Employee.id)
    )
    rows = result.fetchall()
    code_to_id = {str(row[0]).strip(): row[2] for row in rows if row[0]}
    email_to_id = {str(row[1]).strip().lower(): row[2] for row in rows if row[1]}
    return code_to_id, email_to_id


def _prepare_row(record: CSVAttendanceRowSchema, emp_id: int) -> dict:
    """Convert a validated schema record into a flat dict for bulk insert."""
    status = record.status
    is_late = record.is_late
    if status == "LATE":
        is_late = True

    if status in _NON_WORKING:
        first_in = None
        last_out = None
        gross_hrs = None
        net_hrs = None
    else:
        first_in = record.first_in
        last_out = record.last_out
        gross_hrs = record.computed_work_hours_td
        net_hrs = gross_hrs

    return {
        "employee_id": emp_id,
        "log_date": record.log_date,
        "first_in": first_in,
        "last_out": last_out,
        "gross_work_hrs": gross_hrs,
        "net_work_hrs": net_hrs,
        "status": status,
        "is_late": is_late,
        "data_source": "MANUAL_CSV",
    }


async def _bulk_upsert_pg(db: AsyncSession, rows: List[dict]) -> Tuple[int, int]:
    """
    PostgreSQL bulk upsert using INSERT ... ON CONFLICT DO UPDATE.
    Processes in chunks of 500 for memory efficiency.
    Returns (inserted_count, updated_count).
    """
    if not rows:
        return 0, 0

    CHUNK = 500
    total_inserted = 0
    total_updated = 0

    for i in range(0, len(rows), CHUNK):
        chunk = rows[i:i + CHUNK]

        # Build VALUES clause with parameters
        values_parts = []
        params = {}
        for j, row in enumerate(chunk):
            prefix = f"r{i + j}"
            values_parts.append(
                f"(:{prefix}_eid, :{prefix}_date, :{prefix}_fin, :{prefix}_lout, "
                f":{prefix}_gwh, :{prefix}_nwh, :{prefix}_stat, :{prefix}_late, "
                f":{prefix}_src)"
            )
            params[f"{prefix}_eid"] = row["employee_id"]
            params[f"{prefix}_date"] = row["log_date"]
            params[f"{prefix}_fin"] = row["first_in"]
            params[f"{prefix}_lout"] = row["last_out"]
            params[f"{prefix}_gwh"] = row["gross_work_hrs"]
            params[f"{prefix}_nwh"] = row["net_work_hrs"]
            params[f"{prefix}_stat"] = row["status"]
            params[f"{prefix}_late"] = row["is_late"]
            params[f"{prefix}_src"] = row["data_source"]

        sql = f"""
            INSERT INTO attendance_logs
                (employee_id, log_date, first_in, last_out,
                 gross_work_hrs, net_work_hrs, status, is_late, data_source)
            VALUES {', '.join(values_parts)}
            ON CONFLICT (employee_id, log_date) DO UPDATE SET
                first_in = EXCLUDED.first_in,
                last_out = EXCLUDED.last_out,
                gross_work_hrs = EXCLUDED.gross_work_hrs,
                net_work_hrs = EXCLUDED.net_work_hrs,
                status = EXCLUDED.status,
                is_late = EXCLUDED.is_late,
                data_source = EXCLUDED.data_source,
                updated_at = NOW()
        """

        result = await db.execute(text(sql), params)
        # PostgreSQL returns rowcount for all affected rows
        affected = result.rowcount if result.rowcount else len(chunk)
        # Approximate: all are "upserted" — we count chunk size as updated
        total_updated += affected

    return 0, total_updated


async def _bulk_upsert_orm(db: AsyncSession, rows: List[dict]) -> Tuple[int, int]:
    """
    ORM fallback for SQLite: uses select-then-merge pattern.
    Slower but compatible with any backend.
    """
    inserted = 0
    updated = 0

    for row in rows:
        result = await db.execute(
            select(AttendanceLog).where(
                AttendanceLog.employee_id == row["employee_id"],
                AttendanceLog.log_date == row["log_date"],
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            for key, val in row.items():
                setattr(existing, key, val)
            updated += 1
        else:
            db.add(AttendanceLog(**row))
            inserted += 1

    return inserted, updated


async def upsert_csv_batch(
    db: AsyncSession,
    records: List[CSVAttendanceRowSchema],
    filename: str,
) -> Tuple[CSVUploadResult, Set[int], Set[Tuple[int, int]]]:
    """
    Bulk upsert CSV records. Uses PostgreSQL ON CONFLICT for speed,
    falls back to ORM for SQLite.

    Returns:
        (result, affected_employee_ids, affected_months)
    """
    t0 = time.time()

    result = CSVUploadResult(
        filename=filename,
        total_rows=len(records),
        validated=len(records),
    )

    code_to_id, email_to_id = await _build_employee_maps(db)
    logger.info("Employee maps: %d by code, %d by email", len(code_to_id), len(email_to_id))

    affected_employees: Set[int] = set()
    affected_months: Set[Tuple[int, int]] = set()
    bulk_rows: List[dict] = []

    # Phase 1: Map records to employee IDs (pure Python, fast)
    for record in records:
        emp_id = None
        if record.employee_code:
            emp_id = code_to_id.get(record.employee_code)
        if emp_id is None and record.email:
            emp_id = email_to_id.get(record.email.strip().lower())

        if emp_id is None:
            identifier = record.employee_code or record.email or "Unknown"
            result.error_messages.append(
                f"Row {record.source_row}: Employee '{identifier}' not found"
            )
            result.errors += 1
            result.skipped += 1
            continue

        try:
            row_dict = _prepare_row(record, emp_id)
            bulk_rows.append(row_dict)
            affected_employees.add(emp_id)
            affected_months.add((record.log_date.month, record.log_date.year))
        except Exception as e:
            result.error_messages.append(
                f"Row {record.source_row}: Prepare failed - {e}"
            )
            result.errors += 1
            result.skipped += 1

    t1 = time.time()
    logger.info("Phase 1 (mapping): %.2fs for %d records → %d bulk rows",
                t1 - t0, len(records), len(bulk_rows))

    # Phase 2: Bulk upsert (single DB round-trip per chunk)
    if bulk_rows:
        try:
            from app.database import _is_sqlite

            if _is_sqlite:
                ins, upd = await _bulk_upsert_orm(db, bulk_rows)
            else:
                ins, upd = await _bulk_upsert_pg(db, bulk_rows)

            result.inserted = ins
            result.updated = upd
            # If PG bulk, all are "upserted" — report total as updated
            if result.inserted == 0 and result.updated == 0:
                result.updated = len(bulk_rows)

            await db.commit()

        except Exception as exc:
            await db.rollback()
            msg = f"Bulk upsert failed: {exc}"
            result.error_messages.append(msg)
            logger.error(msg, exc_info=True)
            return result, set(), set()

    t2 = time.time()
    logger.info(
        "Phase 2 (bulk upsert): %.2fs — inserted=%d updated=%d errors=%d | TOTAL: %.2fs",
        t2 - t1, result.inserted, result.updated, result.errors, t2 - t0,
    )

    return result, affected_employees, affected_months
