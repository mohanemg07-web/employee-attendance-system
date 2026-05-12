"""
Pydantic schemas for validating rows parsed from biometric CSV/XLSX uploads.

The XLSX exported from the Matrix COSEC biometric console has a
non-standard layout — employee sections grouped as:

.. code-block:: text

    Row N:   (None, '1001 - Hemal KI', None, ...)   ← employee header
    Row N+1: (None, 1, 2026-04-15, 'GS', 09:46, 13:03, 'AB', 'AB', '03:17', ...)
    Row N+2: (None, None, None, ...)                 ← blank separator

This schema validates each **data row** after the parser has
extracted and paired employee_code with the punch data.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Timezone constant ──────────────────────────────────────
IST = timezone(timedelta(hours=5, minutes=30))


# ── Status normalisation ──────────────────────────────────

_HALF_STATUS_MAP = {
    "pr": "PRESENT",
    "ab": "ABSENT",
    "wo": "WEEKEND",
    "ph": "HOLIDAY",
    "fb": "PRESENT",
    "rd": "WEEKEND",
    "in": "PRESENT",
    "ol": "ON_LEAVE",
    "hd": "HALF_DAY",
    "lt": "LATE",
}


def derive_status_from_halves(
    first_half: Optional[str],
    second_half: Optional[str],
    has_punches: bool = False,
) -> str:
    """
    Derive a canonical attendance status from 1st Half / 2nd Half codes.

    Rules:
    - Both ABSENT → ABSENT
    - Both PRESENT → PRESENT
    - One PRESENT one ABSENT → HALF_DAY
    - Both WEEKEND → WEEKEND
    - Both HOLIDAY → HOLIDAY
    - Fallback: if punches exist → PRESENT, else ABSENT
    """
    fh = (first_half or "").strip().lower()
    sh = (second_half or "").strip().lower()

    fh_canon = _HALF_STATUS_MAP.get(fh, "")
    sh_canon = _HALF_STATUS_MAP.get(sh, "")

    if fh_canon == "WEEKEND" and sh_canon == "WEEKEND":
        return "WEEKEND"
    if fh_canon == "HOLIDAY" and sh_canon == "HOLIDAY":
        return "HOLIDAY"
    if fh_canon == "ABSENT" and sh_canon == "ABSENT":
        return "ABSENT"
    if fh_canon == "PRESENT" and sh_canon == "PRESENT":
        return "PRESENT"
    if ("PRESENT" in (fh_canon, sh_canon)) and \
       ("ABSENT" in (fh_canon, sh_canon)):
        return "HALF_DAY"
    if fh_canon == "ON_LEAVE" or sh_canon == "ON_LEAVE":
        return "ON_LEAVE"

    # Fallback
    if has_punches:
        return "PRESENT"
    return "ABSENT"


# ── Main row schema ───────────────────────────────────────

class CSVAttendanceRowSchema(BaseModel):
    """
    Validated representation of a single row from the biometric
    attendance CSV/XLSX upload.

    All fields are pre-parsed by the CSV parser before reaching
    this schema, so types here are already canonical Python types.
    """

    employee_code: Optional[str] = Field(
        default=None,
        description="Employee code extracted from the section header (e.g. '1001').",
    )
    email: Optional[str] = Field(
        default=None,
        description="Employee email extracted from the row, used as fallback if code is missing.",
    )
    employee_name: Optional[str] = Field(
        default=None,
        description="Employee name extracted from the section header.",
    )
    log_date: date = Field(
        ...,
        description="Attendance date.",
    )
    shift: Optional[str] = Field(
        default=None,
        description="Shift code (e.g. 'GS' for General Shift).",
    )
    first_in: Optional[datetime] = Field(
        default=None,
        description="First punch-in timestamp (IST).",
    )
    last_out: Optional[datetime] = Field(
        default=None,
        description="Last punch-out timestamp (IST).",
    )
    first_half: Optional[str] = Field(
        default=None,
        description="1st Half status code (PR/AB/WO/PH/etc.).",
    )
    second_half: Optional[str] = Field(
        default=None,
        description="2nd Half status code.",
    )
    gross_work_hrs: Optional[str] = Field(
        default=None,
        description="Gross work hours as HH:MM string.",
    )
    out_time: Optional[str] = Field(
        default=None,
        description="OUT time as HH:MM string.",
    )
    npunch_work_hrs: Optional[str] = Field(
        default=None,
        description="N-Punch work hours as HH:MM string.",
    )
    status_code: Optional[str] = Field(
        default=None,
        description="O/P Code For Status from biometric report.",
    )
    manual_entry: Optional[str] = Field(
        default=None,
        description="Manual Entry flag (Yes/No).",
    )
    reason: Optional[str] = Field(
        default=None,
        description="Reason text.",
    )

    # ── Row number for error reporting ─────────────────────
    source_row: Optional[int] = Field(
        default=None,
        description="Original row number in the uploaded file (for error messages).",
    )

    @model_validator(mode="after")
    def check_identity(self) -> 'CSVAttendanceRowSchema':
        if not self.employee_code and not self.email:
            raise ValueError("Either employee_code or email must be provided.")
        return self

    model_config = {"arbitrary_types_allowed": True}

    # ── Validators ─────────────────────────────────────────

    @field_validator("employee_code", mode="before")
    @classmethod
    def strip_employee_code(cls, v: Any) -> Optional[str]:
        return str(v).strip() if v else None

    @field_validator("email", mode="before")
    @classmethod
    def strip_email(cls, v: Any) -> Optional[str]:
        return str(v).strip() if v else None

    @field_validator("log_date", mode="before")
    @classmethod
    def parse_log_date(cls, v: Any) -> date:
        if isinstance(v, date) and not isinstance(v, datetime):
            return v
        if isinstance(v, datetime):
            return v.date()
        raw = str(v).strip()
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d%m%Y"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
        raise ValueError(f"Cannot parse date: {raw!r}")

    @field_validator("first_in", "last_out", mode="before")
    @classmethod
    def parse_timestamp(cls, v: Any) -> Optional[datetime]:
        if v is None:
            return None
        if isinstance(v, datetime):
            return v.replace(tzinfo=IST) if v.tzinfo is None else v
        raw = str(v).strip()
        if raw in ("", "-", "N/A", "None", "null", "nan"):
            return None
        for fmt in (
            "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M", "%H:%M:%S", "%H:%M",
        ):
            try:
                dt = datetime.strptime(raw, fmt)
                return dt.replace(tzinfo=IST) if dt.tzinfo is None else dt
            except ValueError:
                continue
        return None

    # ── Derived properties ─────────────────────────────────

    @property
    def is_weekend(self) -> bool:
        """Check if the log date falls on Sunday (only Sunday is a non-working day)."""
        return self.log_date.weekday() == 6  # Sunday only

    @property
    def is_late(self) -> bool:
        """Check if first_in is after 09:00 IST."""
        if self.first_in is None:
            return False
        login_time = self.first_in
        if hasattr(login_time, 'hour'):
            return login_time.hour > 9 or (login_time.hour == 9 and login_time.minute > 0)
        return False

    @property
    def computed_status(self) -> str:
        """
        Recompute status from raw data using strict business rules.

        Priority:
        1. Explicit status_code from CSV (if it matches a known canonical status)
        2. Weekend → WEEKEND (non-working)
        3. No first_in → ABSENT (unless half-day codes say ON_LEAVE)
        4. Half-day codes → derive from 1st/2nd half
        5. Fallback: PRESENT if punches exist
        """
        # If an explicit canonical status was provided in the CSV, use it directly
        _CANONICAL_STATUSES = {
            "PRESENT", "ABSENT", "LATE", "HALF_DAY",
            "ON_LEAVE", "WEEKEND", "HOLIDAY",
        }
        if self.status_code and self.status_code.upper() in _CANONICAL_STATUSES:
            return self.status_code.upper()

        if self.is_weekend:
            return "WEEKEND"

        # If half-day codes are available, use the existing derivation
        if self.first_half or self.second_half:
            derived = derive_status_from_halves(
                self.first_half,
                self.second_half,
                has_punches=self.first_in is not None,
            )
            return derived

        # No half-day codes — derive from punches
        if self.first_in is None:
            return "ABSENT"

        return "PRESENT"

    @property
    def status(self) -> str:
        """Derive canonical status from half-day codes and punch presence."""
        return self.computed_status

    @property
    def computed_work_hours_td(self) -> Optional[timedelta]:
        """
        Recompute work hours as timedelta from first_in and last_out.

        Falls back to parsing the gross_work_hrs CSV field if timestamps
        are not available.
        """
        # Prefer recomputation from timestamps
        if self.first_in and self.last_out:
            delta = self.last_out - self.first_in
            if delta.total_seconds() > 0:
                return delta

        # Fallback: parse the CSV-provided gross_work_hrs string
        interval_str = _hhmm_to_interval(self.gross_work_hrs)
        if interval_str:
            match = re.match(
                r"(\d+) hours (\d+) minutes (\d+) seconds", interval_str
            )
            if match:
                return timedelta(
                    hours=int(match.group(1)),
                    minutes=int(match.group(2)),
                    seconds=int(match.group(3)),
                )
        return None

    @property
    def gross_work_hrs_interval(self) -> Optional[str]:
        """Convert HH:MM string to PostgreSQL INTERVAL string."""
        return _hhmm_to_interval(self.gross_work_hrs)

    @property
    def npunch_work_hrs_interval(self) -> Optional[str]:
        """Convert N-Punch HH:MM to PostgreSQL INTERVAL string."""
        return _hhmm_to_interval(self.npunch_work_hrs)

    def __repr__(self) -> str:
        return (
            f"<CSVRow emp={self.employee_code!r} "
            f"date={self.log_date} status={self.status}>"
        )


def _hhmm_to_interval(val: Optional[str]) -> Optional[str]:
    """Convert 'HH:MM' or 'HH:MM:SS' to a PostgreSQL INTERVAL string."""
    if val is None:
        return None
    raw = str(val).strip()
    if raw in ("", "-", "N/A", "None", "null", "nan", "00:00", "0"):
        return None
    # Handle whitespace-only
    if not raw.replace(" ", ""):
        return None
    match = re.match(r"^(\d+):(\d{2})(?::(\d{2}))?$", raw)
    if match:
        h = int(match.group(1))
        m = int(match.group(2))
        s = int(match.group(3) or 0)
        if h == 0 and m == 0 and s == 0:
            return None
        return f"{h} hours {m} minutes {s} seconds"
    return None


# ── Result schema ──────────────────────────────────────────

class CSVUploadResult(BaseModel):
    """Summary of a CSV upload operation."""
    filename: str
    total_rows: int = 0
    validated: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    error_messages: List[str] = Field(default_factory=list)


class CSVValidationError(BaseModel):
    """Structured error for a single row validation failure."""
    row: int
    employee_code: Optional[str] = None
    field: Optional[str] = None
    message: str
