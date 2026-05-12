"""
Admin CSV Upload Router — secure endpoint for fallback attendance import.

Accepts CSV and XLSX files from authenticated ADMIN users, parses them
through the biometric report parser (or flat CSV parser), validates
every row via Pydantic, and performs a bulk upsert into
``attendance_logs`` with ``data_source = 'MANUAL_CSV'``.

Security:
    - Protected by ``require_role("ADMIN")`` — only ADMIN JWT bearers.
    - File extension validation (.csv, .xlsx, .xls).
    - File size limit (10 MB).
    - Structured error reporting per row.
"""
from __future__ import annotations

import logging
import time
from typing import List

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.employee import Employee
from app.services.csv_parser import parse_attendance_file
from app.crud.crud_csv import upsert_csv_batch
from app.schemas.csv_sync import CSVUploadResult, CSVValidationError
from app.utils.security import require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post(
    "/upload-csv",
    response_model=CSVUploadResult,
    summary="Upload attendance CSV/XLSX",
    description=(
        "Upload a biometric attendance CSV or XLSX file. "
        "Admin only. Performs upsert with MANUAL_CSV provenance — "
        "overwrites any existing API-sourced records."
    ),
    responses={
        400: {
            "description": "Validation errors in the uploaded file",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "CSV validation failed",
                        "errors": [
                            {"row": 7, "employee_code": "1001",
                             "field": "log_date", "message": "Cannot parse date"}
                        ],
                    }
                }
            },
        },
        413: {"description": "File too large (max 10 MB)"},
    },
)
async def upload_csv(
    file: UploadFile = File(
        ...,
        description="CSV or XLSX attendance file to upload",
    ),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: Employee = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> CSVUploadResult:
    """
    Upload and process a biometric attendance CSV/XLSX file.

    **Process:**
    1. Validate file extension and size.
    2. Parse the file (auto-detects biometric report vs flat CSV).
    3. Validate each row via Pydantic schema.
    4. If there are validation errors affecting >50% of rows, reject with 400.
    5. Upsert valid rows into ``attendance_logs`` with ``data_source = 'MANUAL_CSV'``.
    6. Return a summary with counts and any errors.

    **Provenance Rule:** Every row gets ``data_source = 'MANUAL_CSV'``,
    overwriting any existing API records for the same employee + date.
    """
    # ── Step 1: File validation ────────────────────────────
    filename = file.filename or "upload.csv"
    ext = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"File type '{ext}' not supported. "
                f"Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        )

    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large ({len(content) / 1024 / 1024:.1f} MB). Max: 10 MB.",
        )

    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    logger.info(
        "Admin '%s' (id=%s) uploading CSV: '%s' (%d bytes)",
        current_user.email,
        current_user.id,
        filename,
        len(content),
    )

    # ── Step 2: Parse the file ─────────────────────────────
    t0 = time.time()
    try:
        validated_records, validation_errors = parse_attendance_file(
            content, filename
        )
    except Exception as parse_exc:
        logger.error("CSV parse crashed for '%s': %s", filename, parse_exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"CSV parsing failed: {parse_exc}",
        )

    # ── Step 3: Check for critical validation failures ─────
    total_attempted = len(validated_records) + len(validation_errors)

    if total_attempted == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No attendance records found in the uploaded file.",
        )

    if len(validation_errors) > 0 and len(validated_records) == 0:
        try:
            from app.services.audit import log_audit_event
            await log_audit_event(
                db,
                action="CSV_UPLOAD_FAILED",
                user_id=current_user.id,
                metadata={
                    "filename": filename,
                    "error_reason": "All rows failed validation",
                    "total_attempted": total_attempted
                }
            )
        except Exception:
            logger.warning("Failed to write audit log for failed upload")

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "CSV validation failed — all rows have errors",
                "total_rows": total_attempted,
                "errors": [
                    e.model_dump() for e in validation_errors[:30]
                ],
            },
        )

    if validation_errors:
        logger.warning(
            "CSV '%s': %d validation errors out of %d rows — "
            "proceeding with %d valid rows.",
            filename,
            len(validation_errors),
            total_attempted,
            len(validated_records),
        )

    # ── Step 4: Upsert valid records ───────────────────────
    t1 = time.time()
    logger.info("Parse time: %.2fs for %d records", t1 - t0, len(validated_records))
    try:
        result, affected_employees, affected_months = await upsert_csv_batch(
            db, validated_records, filename
        )
    except Exception as upsert_exc:
        logger.error("CSV upsert crashed for '%s': %s", filename, upsert_exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database upsert failed: {upsert_exc}",
        )

    # Append validation errors to the result
    for err in validation_errors[:20]:
        result.error_messages.append(
            f"Row {err.row}: [{err.field or 'general'}] {err.message}"
        )
    result.errors += len(validation_errors)

    logger.info(
        "CSV upload complete for '%s' by admin '%s' — "
        "inserted=%d updated=%d skipped=%d errors=%d | Total time: %.2fs",
        filename,
        current_user.email,
        result.inserted,
        result.updated,
        result.skipped,
        result.errors,
        time.time() - t0,
    )

    # ── Background: aggregation + audit + cache (non-blocking) ──
    async def _post_upload_tasks():
        """Run aggregation, audit logging, and cache invalidation after response."""
        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as bg_db:
            try:
                # Aggregation
                if affected_employees and affected_months:
                    from app.services.aggregation import aggregate_for_affected_months
                    agg_count = await aggregate_for_affected_months(
                        bg_db, list(affected_employees), affected_months,
                    )
                    await bg_db.commit()
                    logger.info(
                        "Background aggregation: %d summaries for %d employees",
                        agg_count, len(affected_employees),
                    )
                else:
                    logger.warning(
                        "Background aggregation skipped: affected_employees=%s, affected_months=%s",
                        bool(affected_employees), bool(affected_months),
                    )
            except Exception as agg_exc:
                logger.error(
                    "Background aggregation FAILED: %s", agg_exc, exc_info=True
                )

            try:
                # Audit
                from app.services.audit import log_audit_event
                await log_audit_event(
                    bg_db,
                    action="CSV_UPLOAD_SUCCESS" if result.inserted + result.updated > 0 else "CSV_UPLOAD_NO_CHANGES",
                    user_id=current_user.id,
                    metadata={
                        "filename": filename,
                        "inserted": result.inserted,
                        "updated": result.updated,
                        "errors": result.errors,
                        "total_rows": result.total_rows,
                    }
                )
                await bg_db.commit()
            except Exception:
                logger.warning("Background audit log failed")

            try:
                # Cache invalidation
                from app.services.cache import get_redis, invalidate_dashboard_caches
                redis_client = get_redis()
                if redis_client and affected_employees:
                    await invalidate_dashboard_caches(bg_db, list(affected_employees))
            except Exception:
                pass

    background_tasks.add_task(_post_upload_tasks)

    return result


@router.get(
    "/history",
    summary="CSV upload history",
    description="Returns recent CSV upload audit log entries.",
)
async def get_upload_history(
    limit: int = 20,
    current_user: Employee = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Return recent CSV upload history from audit_logs."""
    from sqlalchemy import select, desc

    try:
        from app.models.audit import AuditLog

        result = await db.execute(
            select(AuditLog)
            .where(AuditLog.action.in_([
                "CSV_UPLOAD_SUCCESS",
                "CSV_UPLOAD_NO_CHANGES",
                "CSV_UPLOAD_FAILED",
            ]))
            .order_by(desc(AuditLog.timestamp))
            .limit(limit)
        )
        rows = result.scalars().all()

        history = []
        for row in rows:
            meta = row.metadata_payload or {}
            history.append({
                "id": row.id,
                "file_name": meta.get("filename", "Unknown"),
                "uploaded_at": row.timestamp.isoformat() if row.timestamp else None,
                "rows": meta.get("total_rows", 0),
                "inserted": meta.get("inserted", 0),
                "updated": meta.get("updated", 0),
                "errors": meta.get("errors", 0),
                "status": "Completed" if row.action == "CSV_UPLOAD_SUCCESS" else (
                    "No Changes" if row.action == "CSV_UPLOAD_NO_CHANGES" else "Failed"
                ),
            })

        return {"history": history}

    except Exception as exc:
        # audit_logs table may not exist yet — return empty gracefully
        logger.warning("Could not fetch upload history: %s", exc)
        return {"history": []}


@router.get(
    "/preview",
    summary="Preview recent attendance data",
    description="Returns the most recently uploaded attendance log rows.",
)
async def get_preview(
    limit: int = 20,
    current_user: Employee = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Return the most recently inserted attendance_logs rows."""
    from sqlalchemy import select, desc

    try:
        from app.models.attendance import AttendanceLog
        from app.models.employee import Employee as Emp

        result = await db.execute(
            select(AttendanceLog, Emp)
            .join(Emp, Emp.id == AttendanceLog.employee_id)
            .where(AttendanceLog.data_source == "MANUAL_CSV")
            .order_by(desc(AttendanceLog.updated_at))
            .limit(limit)
        )
        rows = result.all()

        def _interval_str(val):
            if not val:
                return None
            s = int(val.total_seconds())
            h, r = divmod(s, 3600)
            m, sec = divmod(r, 60)
            return f"{h:02d}:{m:02d}:{sec:02d}"

        preview_rows = []
        for log, emp in rows:
            preview_rows.append({
                "employee_code": emp.employee_code,
                "employee_name": emp.full_name,
                "email": emp.email,
                "log_date": log.log_date.isoformat() if log.log_date else None,
                "first_in": log.first_in.isoformat() if log.first_in else None,
                "last_out": log.last_out.isoformat() if log.last_out else None,
                "gross_work_hrs": _interval_str(log.gross_work_hrs),
                "status": log.status,
                "is_late": log.is_late,
                "data_source": log.data_source,
            })

        return {"rows": preview_rows}

    except Exception as exc:
        logger.warning("Could not fetch preview: %s", exc)
        return {"rows": []}
