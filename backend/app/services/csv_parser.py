"""
CSV/XLSX parser for the biometric attendance upload fallback.

Handles **two** input formats:

1. **Biometric Report XLSX** (Matrix COSEC export) — non-standard grouped layout:
   - Title/meta rows at top (company name, date range, headers)
   - Employee sections: header row ``"1001 - Hemal KI"`` followed by data rows
   - Blank separator rows between employees

2. **Flat CSV** — standard tabular format with columns like
   ``Employee Code, Date, First IN, Last OUT, Status, Gross Work Hrs``

The parser auto-detects the format and normalises all records into
:class:`CSVAttendanceRowSchema` instances for downstream validation
and database upsert.
"""
from __future__ import annotations

import io
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from pydantic import ValidationError

from app.schemas.csv_sync import (
    CSVAttendanceRowSchema,
    CSVValidationError,
    CSVUploadResult,
)

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


# ── Flat CSV column mapping ───────────────────────────────
# Maps common column header variations to canonical field names.
FLAT_COLUMN_MAP = {
    "employee code": "employee_code",
    "emp code": "employee_code",
    "employee_code": "employee_code",
    "employeecode": "employee_code",
    "user-id": "employee_code",
    "userid": "employee_code",
    "employee id": "employee_code",
    "sr no": "_sr_no",

    "email": "email",
    "email id": "email",

    "employee name": "employee_name",
    "emp name": "employee_name",
    "full_name": "employee_name",

    "date": "log_date",
    "attendance date": "log_date",
    "log_date": "log_date",

    "first in": "first_in",
    "first_in": "first_in",
    "in time": "first_in",
    "first-in": "first_in",

    "last out": "last_out",
    "last_out": "last_out",
    "out time": "last_out",
    "last-out": "last_out",

    "1st half": "first_half",
    "first half": "first_half",
    "first_half": "first_half",

    "2nd half": "second_half",
    "second half": "second_half",
    "second_half": "second_half",

    "gross work hrs": "gross_work_hrs",
    "gross_work_hrs": "gross_work_hrs",
    "work hours": "gross_work_hrs",
    "gross-work-hrs": "gross_work_hrs",
    "total hours": "gross_work_hrs",

    "n-punch work hrs": "npunch_work_hrs",
    "npunch_work_hrs": "npunch_work_hrs",

    # Extra punch-out synonyms (populate ``out_time`` on schema via flat parser fallback)
    "clock out": "out_time",

    "shift": "shift",

    "o/p code for status": "status_code",
    "status_code": "status_code",
    "status": "status",
    "attendance status": "status",

    "man entry": "manual_entry",
    "manual_entry": "manual_entry",

    "reason": "reason",
}


def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename DataFrame columns using the flexible mapping."""
    rename_map = {}
    for col in df.columns:
        # Strip whitespace and newlines from column names
        normalised = re.sub(r"\s+", " ", str(col).strip().lower())
        if normalised in FLAT_COLUMN_MAP:
            rename_map[col] = FLAT_COLUMN_MAP[normalised]
    return df.rename(columns=rename_map)


# ── Time parsers ──────────────────────────────────────────

def parse_time(val: Any, log_date: date) -> Optional[datetime]:
    """
    Parse a time value and combine with log_date to produce
    a timezone-aware datetime.

    Handles: datetime objects, 'HH:MM:SS', 'HH:MM', and full timestamps.
    Returns None for missing/empty values.
    """
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None

    if isinstance(val, datetime):
        dt = val
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        return dt

    val_str = str(val).strip()
    if val_str in ("", "-", "N/A", "None", "null", "nan"):
        return None

    # Time-only formats
    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p"):
        try:
            t = datetime.strptime(val_str, fmt).time()
            return datetime.combine(log_date, t, tzinfo=IST)
        except ValueError:
            continue

    # Full timestamp
    try:
        dt = pd.to_datetime(val_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        return dt
    except Exception:
        return None


def parse_work_hours(val: Any) -> Optional[str]:
    """
    Parse work hours into a clean HH:MM string.

    Handles: 'HH:MM:SS', 'HH:MM', decimal hours, datetime objects.
    Returns None for empty/zero values.
    """
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None

    val_str = str(val).strip()
    if val_str in ("", "-", "N/A", "None", "null", "nan"):
        return None

    # Whitespace-only
    if not val_str.replace(" ", ""):
        return None

    # Already HH:MM or HH:MM:SS format
    match = re.match(r"^(\d+):(\d{2})(?::(\d{2}))?$", val_str)
    if match:
        return val_str

    # Decimal hours
    try:
        hrs = float(val_str)
        h = int(hrs)
        m = int((hrs - h) * 60)
        return f"{h:02d}:{m:02d}"
    except ValueError:
        return None


# ── Format detection ──────────────────────────────────────

_EMPLOYEE_HEADER_PATTERN = re.compile(
    r"^\s*(\d+)\s*-\s*(.+)$"
)


def _is_biometric_report(rows: List[tuple]) -> bool:
    """
    Detect if the data is a biometric report by checking for
    employee header patterns like '1001 - Hemal KI'.
    """
    for row in rows[:15]:
        for cell in row:
            if cell is not None and isinstance(cell, str):
                if _EMPLOYEE_HEADER_PATTERN.match(cell.strip()):
                    return True
    return False


# ── Biometric Report Parser ──────────────────────────────

def _parse_biometric_report(
    rows: List[tuple],
    filename: str,
) -> Tuple[List[CSVAttendanceRowSchema], List[CSVValidationError]]:
    """
    Parse a Matrix COSEC biometric report XLSX.

    The report has the layout:
    - Row 0: Company name
    - Row 1: Report title with date range
    - Row 2: Run by / Date info
    - Row 3: Column headers (Sr No, Date, Shift, First IN, ...)
    - Rows 4+: Alternating employee-header + data + blank rows

    Employee header: ``(None, '1001 - Hemal KI', None, ...)``
    Data row:        ``(None, 1, datetime(2026,4,15), 'GS', datetime(...), ...)``
    """
    validated: List[CSVAttendanceRowSchema] = []
    errors: List[CSVValidationError] = []

    current_employee_code: Optional[str] = None
    current_employee_name: Optional[str] = None

    for row_idx, row in enumerate(rows):
        # Skip rows with all None values
        if all(cell is None for cell in row):
            continue

        # Check for employee header: cell at index 1 matches "CODE - NAME"
        cell_1 = row[1] if len(row) > 1 else None
        if cell_1 is not None and isinstance(cell_1, str):
            match = _EMPLOYEE_HEADER_PATTERN.match(cell_1.strip())
            if match:
                current_employee_code = match.group(1).strip()
                current_employee_name = match.group(2).strip()
                continue

        # Skip if no employee context yet
        if current_employee_code is None:
            continue

        # Check if this is a data row: cell at index 1 should be a number (Sr No)
        # and cell at index 2 should be a date
        cell_sr = row[1] if len(row) > 1 else None
        cell_date = row[2] if len(row) > 2 else None

        if cell_sr is None or cell_date is None:
            continue

        # Sr No should be numeric
        try:
            int(cell_sr)
        except (ValueError, TypeError):
            continue

        # cell_date should be a date/datetime
        if not isinstance(cell_date, (date, datetime)):
            continue

        # This is a valid data row — extract fields
        # Columns from the header row (index 3):
        # 0: None, 1: Sr No, 2: Date, 3: Shift, 4: First IN, 5: Last OUT,
        # 6: 1st Half, 7: 2nd Half, 8: Gross Work Hrs, 9: OUT Time,
        # 10: N-Punch Work Hrs, 11: O/P Code, 12: Man Entry, 13: Reason

        log_date = cell_date.date() if isinstance(cell_date, datetime) else cell_date

        first_in = row[4] if len(row) > 4 else None
        last_out = row[5] if len(row) > 5 else None
        first_half = str(row[6]).strip() if len(row) > 6 and row[6] is not None else None
        second_half = str(row[7]).strip() if len(row) > 7 and row[7] is not None else None
        gross_work = str(row[8]).strip() if len(row) > 8 and row[8] is not None else None
        out_time = str(row[9]).strip() if len(row) > 9 and row[9] is not None else None
        npunch_hrs = str(row[10]).strip() if len(row) > 10 and row[10] is not None else None
        status_code = str(row[11]).strip() if len(row) > 11 and row[11] is not None else None
        man_entry = str(row[12]).strip() if len(row) > 12 and row[12] is not None else None
        reason = str(row[13]).strip() if len(row) > 13 and row[13] is not None else None

        # Parse timestamps
        parsed_in = parse_time(first_in, log_date)
        parsed_out = parse_time(last_out, log_date)

        try:
            record = CSVAttendanceRowSchema(
                employee_code=current_employee_code,
                employee_name=current_employee_name,
                log_date=log_date,
                shift=str(row[3]).strip() if len(row) > 3 and row[3] is not None else None,
                first_in=parsed_in,
                last_out=parsed_out,
                first_half=first_half,
                second_half=second_half,
                gross_work_hrs=parse_work_hours(gross_work),
                out_time=parse_work_hours(out_time),
                npunch_work_hrs=parse_work_hours(npunch_hrs),
                status_code=status_code,
                manual_entry=man_entry,
                reason=reason if reason and reason != "None" else None,
                source_row=row_idx + 1,
            )
            validated.append(record)
        except ValidationError as exc:
            for err in exc.errors():
                errors.append(CSVValidationError(
                    row=row_idx + 1,
                    employee_code=current_employee_code,
                    field=err.get("loc", [None])[-1],
                    message=err.get("msg", str(err)),
                ))

    return validated, errors


# ── Flat CSV Parser ───────────────────────────────────────

def _parse_flat_csv(
    df: pd.DataFrame,
    filename: str,
) -> Tuple[List[CSVAttendanceRowSchema], List[CSVValidationError]]:
    """
    Parse a standard flat CSV with columns:
    Employee Code, Date, First IN, Last OUT, Status, Gross Work Hrs, etc.
    """
    df = normalise_columns(df)

    validated: List[CSVAttendanceRowSchema] = []
    errors: List[CSVValidationError] = []

    # Check for required column
    if "employee_code" not in df.columns and "_sr_no" not in df.columns and "email" not in df.columns:
        errors.append(CSVValidationError(
            row=0,
            message="Missing required column: Employee Code or Email",
        ))
        return validated, errors

    if "log_date" not in df.columns:
        errors.append(CSVValidationError(
            row=0,
            message="Missing required column: Date",
        ))
        return validated, errors

    for idx, row in df.iterrows():
        row_num = idx + 2  # 1-indexed + header row

        emp_code = str(row.get("employee_code", "")).strip()
        if emp_code in ("nan", "None", ""):
            emp_code = None

        email_val = str(row.get("email", "")).strip()
        if email_val in ("nan", "None", ""):
            email_val = None

        if not emp_code and not email_val:
            continue

        try:
            raw_date = row.get("log_date")
            log_date = pd.to_datetime(raw_date).date()
        except Exception:
            errors.append(CSVValidationError(
                row=row_num,
                employee_code=emp_code,
                field="log_date",
                message=f"Invalid date: {row.get('log_date')!r}",
            ))
            continue

        # Read the explicit status from CSV before parsing times
        csv_status = str(row.get("status", "")).strip().upper()
        if csv_status in ("NAN", "NONE", ""):
            csv_status = None

        # Force first_in / last_out to None for non-working statuses
        _NON_PUNCH_STATUSES = {"HOLIDAY", "WEEKEND", "ABSENT", "ON_LEAVE"}
        if csv_status in _NON_PUNCH_STATUSES:
            first_in = None
            last_out = None
        else:
            first_in = parse_time(row.get("first_in"), log_date)
            raw_out = row.get("last_out")
            if raw_out is None or (
                isinstance(raw_out, float) and pd.isna(raw_out)
            ) or (
                isinstance(raw_out, str) and not str(raw_out).strip()
            ):
                raw_out = row.get("out_time")
            last_out = parse_time(raw_out, log_date)

        try:
            record = CSVAttendanceRowSchema(
                employee_code=emp_code,
                email=email_val,
                employee_name=str(row.get("employee_name", "")).strip() or None,
                log_date=log_date,
                shift=str(row.get("shift", "")).strip() or None,
                first_in=first_in,
                last_out=last_out,
                first_half=str(row.get("first_half", "")).strip() or None,
                second_half=str(row.get("second_half", "")).strip() or None,
                gross_work_hrs=parse_work_hours(row.get("gross_work_hrs")),
                npunch_work_hrs=parse_work_hours(row.get("npunch_work_hrs")),
                status_code=csv_status,
                source_row=row_num,
            )
            validated.append(record)
        except ValidationError as exc:
            for err in exc.errors():
                errors.append(CSVValidationError(
                    row=row_num,
                    employee_code=emp_code,
                    field=err.get("loc", [None])[-1],
                    message=err.get("msg", str(err)),
                ))

    logger.info(
        "Flat CSV '%s': parsed %d valid records, %d errors out of %d rows.",
        filename, len(validated), len(errors), len(df),
    )
    return validated, errors


# ── Main entry point ──────────────────────────────────────

def parse_attendance_file(
    file_content: bytes,
    filename: str,
) -> Tuple[List[CSVAttendanceRowSchema], List[CSVValidationError]]:
    """
    Parse an uploaded attendance file (CSV or XLSX) and return
    validated records + any validation errors.

    Auto-detects format:
    - Biometric report XLSX (grouped employee sections)
    - Flat CSV/XLSX (tabular format)

    Args:
        file_content: Raw bytes of the uploaded file.
        filename: Original filename (used for format detection).

    Returns:
        Tuple of (validated_records, validation_errors).
    """
    try:
        if filename.lower().endswith((".xlsx", ".xls")):
            import openpyxl
            wb = openpyxl.load_workbook(
                io.BytesIO(file_content),
                read_only=True,
                data_only=True,
            )
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            wb.close()

            if _is_biometric_report(rows):
                logger.info(
                    "Detected biometric report format in '%s' "
                    "(%d rows).",
                    filename,
                    len(rows),
                )
                return _parse_biometric_report(rows, filename)
            else:
                # Flat XLSX — read with pandas
                df = pd.read_excel(io.BytesIO(file_content))
                return _parse_flat_csv(df, filename)
        else:
            # CSV
            df = pd.read_csv(io.BytesIO(file_content))
            return _parse_flat_csv(df, filename)

    except Exception as exc:
        logger.exception("Failed to read file '%s': %s", filename, exc)
        return [], [CSVValidationError(
            row=0,
            message=f"Failed to read file: {exc}",
        )]
