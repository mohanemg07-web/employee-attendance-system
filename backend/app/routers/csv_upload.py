"""
CSV upload router — Legacy endpoint (backward compatibility).

.. deprecated:: 2026-04-29
    Prefer ``/admin/upload-csv`` via ``app.routers.admin_csv`` which uses
    the new biometric-report-aware parser and structured Pydantic validation.

    This endpoint is retained for backward compatibility with the
    existing frontend AdminPanel component.
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.employee import Employee
from app.services.csv_parser import parse_attendance_file
from app.crud.crud_csv import upsert_csv_batch
from app.utils.security import require_role

router = APIRouter(prefix="/admin", tags=["Admin"])

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


@router.post("/upload-csv-legacy")
async def upload_csv_legacy(
    file: UploadFile = File(...),
    current_user: Employee = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Legacy CSV upload endpoint. Use /admin/upload-csv instead."""
    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{ext}' not supported. Use .csv, .xlsx, or .xls",
        )

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large (max 10MB)",
        )

    records, errors = parse_attendance_file(content, file.filename)

    if not records:
        return {
            "filename": file.filename,
            "total_rows": 0,
            "inserted": 0,
            "updated": 0,
            "skipped": 0,
            "errors": [e.message for e in errors[:20]],
        }

    result = await upsert_csv_batch(db, records, file.filename)
    return result.model_dump()
