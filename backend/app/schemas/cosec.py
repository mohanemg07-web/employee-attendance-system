"""
Internal Pydantic schemas for validating parsed Matrix COSEC API responses.

These schemas act as a validation & normalisation boundary between the raw
API data (XML/JSON dicts) and the SQLAlchemy ORM layer. Every record
fetched from COSEC is validated through ``CosecDailyAttendanceRecord``
before being passed to the upsert logic.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Timezone constant ──────────────────────────────────────
IST = timezone(timedelta(hours=5, minutes=30))


class AttendanceStatus(str, Enum):
    """Canonical attendance status values used across the system."""
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    LATE = "LATE"
    HALF_DAY = "HALF_DAY"
    WEEKEND = "WEEKEND"
    ON_LEAVE = "ON_LEAVE"
    HOLIDAY = "HOLIDAY"


# Mapping of raw COSEC status strings → canonical enum values
_STATUS_ALIAS_MAP: Dict[str, AttendanceStatus] = {
    "present": AttendanceStatus.PRESENT,
    "p": AttendanceStatus.PRESENT,
    "absent": AttendanceStatus.ABSENT,
    "a": AttendanceStatus.ABSENT,
    "late": AttendanceStatus.LATE,
    "l": AttendanceStatus.LATE,
    "half day": AttendanceStatus.HALF_DAY,
    "half_day": AttendanceStatus.HALF_DAY,
    "halfday": AttendanceStatus.HALF_DAY,
    "hd": AttendanceStatus.HALF_DAY,
    "weekend": AttendanceStatus.WEEKEND,
    "wo": AttendanceStatus.WEEKEND,
    "weekly off": AttendanceStatus.WEEKEND,
    "on leave": AttendanceStatus.ON_LEAVE,
    "on_leave": AttendanceStatus.ON_LEAVE,
    "leave": AttendanceStatus.ON_LEAVE,
    "ol": AttendanceStatus.ON_LEAVE,
    "holiday": AttendanceStatus.HOLIDAY,
    "h": AttendanceStatus.HOLIDAY,
}


class CosecDailyAttendanceRecord(BaseModel):
    """
    Validated & normalised representation of a single daily attendance
    record from the Matrix COSEC API.

    Accepts flexible input formats (DD/MM/YYYY, YYYY-MM-DD, DDMMYYYY for
    dates; HH:MM, HH:MM:SS, full ISO timestamps for times) and converts
    them into canonical Python types.
    """

    employee_code: str = Field(
        ...,
        min_length=1,
        description="Employee code / user-id from the COSEC system.",
    )
    log_date: date = Field(
        ...,
        description="Attendance date, normalised to Python date.",
    )
    first_in: Optional[datetime] = Field(
        default=None,
        description="First punch-in timestamp (timezone-aware IST).",
    )
    last_out: Optional[datetime] = Field(
        default=None,
        description="Last punch-out timestamp (timezone-aware IST).",
    )
    work_hours: Optional[timedelta] = Field(
        default=None,
        description="Gross working hours as timedelta.",
    )
    status: AttendanceStatus = Field(
        default=AttendanceStatus.PRESENT,
        description="Normalised attendance status.",
    )
    raw_payload: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Original raw record dict for auditing.",
    )

    model_config = {"arbitrary_types_allowed": True}

    # ── Validators ─────────────────────────────────────────

    @field_validator("employee_code", mode="before")
    @classmethod
    def strip_employee_code(cls, v: Any) -> str:
        """Strip whitespace and coerce to string."""
        return str(v).strip()

    @field_validator("log_date", mode="before")
    @classmethod
    def parse_log_date(cls, v: Any) -> date:
        """
        Parse date from multiple formats:
        - DD/MM/YYYY
        - YYYY-MM-DD
        - DDMMYYYY
        - Already a ``date`` instance
        """
        if isinstance(v, date):
            return v
        if isinstance(v, datetime):
            return v.date()

        raw = str(v).strip()
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d%m%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
        raise ValueError(f"Cannot parse date: '{raw}'")

    @field_validator("first_in", "last_out", mode="before")
    @classmethod
    def parse_punch_time(cls, v: Any) -> Optional[datetime]:
        """
        Parse punch timestamp from various COSEC formats.
        Returns timezone-aware (IST) datetime or None.
        """
        if v is None:
            return None

        raw = str(v).strip()
        if raw in ("", "-", "N/A", "None", "null", "nan"):
            return None

        # If already a datetime, ensure timezone-aware
        if isinstance(v, datetime):
            return v.replace(tzinfo=IST) if v.tzinfo is None else v

        # Try full timestamp formats first
        for fmt in (
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S%z",
        ):
            try:
                dt = datetime.strptime(raw, fmt)
                return dt.replace(tzinfo=IST) if dt.tzinfo is None else dt
            except ValueError:
                continue

        # Time-only formats (will be combined with log_date in model_validator)
        for fmt in ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p"):
            try:
                t = datetime.strptime(raw, fmt).time()
                # Return a sentinel datetime at epoch; model_validator will fix the date
                return datetime.combine(date(1970, 1, 1), t, tzinfo=IST)
            except ValueError:
                continue

        return None

    @field_validator("work_hours", mode="before")
    @classmethod
    def parse_work_hours(cls, v: Any) -> Optional[timedelta]:
        """
        Parse work hours from COSEC formats:
        - "HH:MM:SS" or "HH:MM"
        - Decimal hours (e.g. "8.5")
        - Already a timedelta
        - PostgreSQL interval string (e.g. "8 hours 30 minutes")
        """
        if v is None:
            return None
        if isinstance(v, timedelta):
            return v

        raw = str(v).strip()
        if raw in ("", "-", "N/A", "None", "null", "nan", "0"):
            return None

        # HH:MM:SS or HH:MM
        if ":" in raw:
            parts = raw.split(":")
            try:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = int(parts[2]) if len(parts) > 2 else 0
                return timedelta(hours=hours, minutes=minutes, seconds=seconds)
            except (ValueError, IndexError):
                pass

        # Decimal hours
        try:
            decimal_hrs = float(raw)
            return timedelta(hours=decimal_hrs)
        except ValueError:
            pass

        # PostgreSQL-style interval: "X hours Y minutes Z seconds"
        interval_pattern = re.compile(
            r"(?:(\d+)\s*hours?)?\s*(?:(\d+)\s*min(?:ute)?s?)?\s*(?:(\d+)\s*sec(?:ond)?s?)?",
            re.IGNORECASE,
        )
        match = interval_pattern.fullmatch(raw.strip())
        if match and any(match.groups()):
            h = int(match.group(1) or 0)
            m = int(match.group(2) or 0)
            s = int(match.group(3) or 0)
            return timedelta(hours=h, minutes=m, seconds=s)

        return None

    @field_validator("status", mode="before")
    @classmethod
    def normalise_status(cls, v: Any) -> AttendanceStatus:
        """Map raw COSEC status strings to canonical AttendanceStatus enum."""
        if isinstance(v, AttendanceStatus):
            return v
        raw = str(v).strip().lower()
        return _STATUS_ALIAS_MAP.get(raw, AttendanceStatus.PRESENT)

    @model_validator(mode="after")
    def fix_punch_dates(self) -> "CosecDailyAttendanceRecord":
        """
        If punch times were parsed as time-only (date=1970-01-01),
        combine them with the record's ``log_date``.
        """
        sentinel_date = date(1970, 1, 1)
        if self.first_in and self.first_in.date() == sentinel_date:
            self.first_in = datetime.combine(
                self.log_date, self.first_in.time(), tzinfo=IST
            )
        if self.last_out and self.last_out.date() == sentinel_date:
            self.last_out = datetime.combine(
                self.log_date, self.last_out.time(), tzinfo=IST
            )
        return self


class CosecSyncResult(BaseModel):
    """Summary of a COSEC → database sync operation."""
    total_fetched: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    error_messages: list[str] = Field(default_factory=list)
