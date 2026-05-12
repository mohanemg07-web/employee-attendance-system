"""
Pydantic schemas for validating parsed Matrix COSEC Monthly Attendance data.

These schemas match the pipe-delimited response from the COSEC API endpoint
``/api.svc/v2/attendance-monthly`` (see Matrix COSEC Web API User Guide,
pp. 106–113).

Response tag names used for mapping:
    USERID, USERNAME, PYEAR, PMONTH, PRDAYS, ABDAYS, WODAYS, PHDAYS,
    PLDAYS, TRDAYS, ULDAYS, LODAYS, LATEIN, LATEIN_HHMM, EARLYOUT,
    EARLYOUT_HHMM, WORKTIME, WORKTIME_HHMM, OVERTIME, NETWORKTIME,
    late_in_count, early_out_count, short_name, integration_reference
"""
from __future__ import annotations

import re
from datetime import timedelta
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Field-name mapping ─────────────────────────────────────
# Maps pipe-header tag names (case-insensitive) to our canonical fields.
MONTHLY_TAG_MAP: Dict[str, str] = {
    "userid":              "employee_code",
    "UserID":              "employee_code",
    "USERID":              "employee_code",
    "user-id":             "employee_code",
    "username":            "employee_name",
    "UserName":            "employee_name",
    "USERNAME":            "employee_name",
    "short_name":          "short_name",
    "pyear":               "year",
    "PYear":               "year",
    "PYEAR":               "year",
    "pmonth":              "month",
    "PMonth":              "month",
    "PMONTH":              "month",
    "prdays":              "present_days",
    "PRDays":              "present_days",
    "PRDAYS":              "present_days",
    "abdays":              "absent_days",
    "ABDays":              "absent_days",
    "ABDAYS":              "absent_days",
    "wodays":              "weekoff_days",
    "WODAYS":              "weekoff_days",
    "phdays":              "holiday_days",
    "PHDAYS":              "holiday_days",
    "pldays":              "paid_leave_days",
    "PLDays":              "paid_leave_days",
    "PLDAYS":              "paid_leave_days",
    "trdays":              "tour_days",
    "TRDays":              "tour_days",
    "TRDAYS":              "tour_days",
    "uldays":              "unpaid_leave_days",
    "ULDAYS":              "unpaid_leave_days",
    "lodays":              "layoff_days",
    "LODAYS":              "layoff_days",
    "worktime_hhmm":       "work_hours_hhmm",
    "WorkTime_HHMM":       "work_hours_hhmm",
    "WORKTIME_HHMM":       "work_hours_hhmm",
    "worktime":            "work_hours_minutes",
    "WORKTIME":            "work_hours_minutes",
    "networktime":         "net_work_minutes",
    "NETWORKTIME":         "net_work_minutes",
    "overtime":            "overtime_minutes",
    "OVERTIME":            "overtime_minutes",
    "latein":              "late_in_minutes",
    "LATEIN":              "late_in_minutes",
    "latein_hhmm":         "late_in_hhmm",
    "LATEIN_HHMM":         "late_in_hhmm",
    "earlyout":            "early_out_minutes",
    "EARLYOUT":            "early_out_minutes",
    "earlyout_hhmm":       "early_out_hhmm",
    "EARLYOUT_HHMM":       "early_out_hhmm",
    "late_in_count":       "late_in_count",
    "early_out_count":     "early_out_count",
}


def remap_monthly_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Translate raw COSEC tag names into canonical schema field names.

    Unmapped keys are preserved in ``raw_payload`` for auditing.
    """
    mapped: Dict[str, Any] = {}
    for key, value in raw.items():
        canonical = MONTHLY_TAG_MAP.get(key)
        if canonical:
            mapped[canonical] = value
    mapped["raw_payload"] = raw
    return mapped


# ── Helpers ────────────────────────────────────────────────

def _parse_hhmm_to_timedelta(val: Any) -> Optional[timedelta]:
    """
    Parse ``HH:MM``, ``HHH:MM``, or ``HHHHHH:MM`` formatted string
    into a ``timedelta``. Returns ``None`` for empty/invalid values.
    """
    if val is None:
        return None
    raw = str(val).strip()
    if raw in ("", "-", "N/A", "None", "null", "nan", "000:00"):
        return None
    match = re.match(r"^(\d+):(\d{2})$", raw)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        return timedelta(hours=hours, minutes=minutes)
    return None


def _safe_float(val: Any, default: float = 0.0) -> float:
    """Coerce to float, returning ``default`` on failure."""
    if val is None:
        return default
    try:
        return float(str(val).strip())
    except (ValueError, TypeError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    """Coerce to int, returning ``default`` on failure."""
    if val is None:
        return default
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return default


# ── Main Schema ────────────────────────────────────────────

class MonthlyAttendanceSyncSchema(BaseModel):
    """
    Validated representation of a single monthly attendance record
    from the Matrix COSEC API.

    All day-count fields accept ``float`` (COSEC returns multiples of 0.5)
    and are rounded to ``int`` for storage in ``attendance_monthly``.
    """

    employee_code: str = Field(
        ..., min_length=1,
        description="User ID from COSEC (tag: USERID).",
    )
    employee_name: Optional[str] = Field(
        default=None,
        description="User display name (tag: USERNAME).",
    )
    short_name: Optional[str] = Field(
        default=None,
        description="Short name (tag: short_name).",
    )
    month: int = Field(
        ..., ge=1, le=12,
        description="Process month 1–12 (tag: PMONTH).",
    )
    year: int = Field(
        ..., ge=2000, le=2100,
        description="Process year (tag: PYEAR).",
    )

    # ── Day counts (COSEC returns multiples of 0.5) ────────
    present_days: float = Field(default=0.0, description="Present days (PRDAYS).")
    absent_days: float = Field(default=0.0, description="Absent days (ABDAYS).")
    weekoff_days: float = Field(default=0.0, description="Week-off days (WODAYS).")
    holiday_days: float = Field(default=0.0, description="Public holiday days (PHDAYS).")
    paid_leave_days: float = Field(default=0.0, description="Paid leave days (PLDAYS).")
    tour_days: float = Field(default=0.0, description="Tour days (TRDAYS).")
    unpaid_leave_days: float = Field(default=0.0, description="Unpaid leave days (ULDAYS).")
    layoff_days: float = Field(default=0.0, description="Lay-off days (LODAYS).")

    # ── Time metrics ───────────────────────────────────────
    work_hours_hhmm: Optional[str] = Field(
        default=None,
        description="Total work time as HH:MM or HHH:MM (tag: WORKTIME_HHMM).",
    )
    work_hours_minutes: Optional[float] = Field(
        default=None,
        description="Total work time in minutes (tag: WORKTIME).",
    )
    net_work_minutes: Optional[float] = Field(
        default=None,
        description="Net work time in minutes (tag: NETWORKTIME).",
    )
    overtime_minutes: Optional[float] = Field(
        default=None,
        description="Total overtime in minutes (tag: OVERTIME).",
    )
    late_in_minutes: Optional[float] = Field(
        default=None,
        description="Total late-in duration in minutes (tag: LATEIN).",
    )
    late_in_hhmm: Optional[str] = Field(
        default=None,
        description="Total late-in as HH:MM (tag: LATEIN_HHMM).",
    )
    early_out_minutes: Optional[float] = Field(
        default=None,
        description="Total early-out duration in minutes (tag: EARLYOUT).",
    )
    early_out_hhmm: Optional[str] = Field(
        default=None,
        description="Total early-out as HH:MM (tag: EARLYOUT_HHMM).",
    )
    late_in_count: int = Field(default=0, description="Late-in count (0–99).")
    early_out_count: int = Field(default=0, description="Early-out count (0–99).")

    # ── Audit ──────────────────────────────────────────────
    raw_payload: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Original raw record for debugging.",
    )

    model_config = {"arbitrary_types_allowed": True}

    # ── Validators ─────────────────────────────────────────

    @field_validator("employee_code", mode="before")
    @classmethod
    def strip_employee_code(cls, v: Any) -> str:
        return str(v).strip()

    @field_validator("month", mode="before")
    @classmethod
    def coerce_month(cls, v: Any) -> int:
        return _safe_int(v)

    @field_validator("year", mode="before")
    @classmethod
    def coerce_year(cls, v: Any) -> int:
        return _safe_int(v)

    @field_validator(
        "present_days", "absent_days", "weekoff_days", "holiday_days",
        "paid_leave_days", "tour_days", "unpaid_leave_days", "layoff_days",
        mode="before",
    )
    @classmethod
    def coerce_day_count(cls, v: Any) -> float:
        return _safe_float(v)

    @field_validator(
        "work_hours_minutes", "net_work_minutes", "overtime_minutes",
        "late_in_minutes", "early_out_minutes",
        mode="before",
    )
    @classmethod
    def coerce_minutes(cls, v: Any) -> Optional[float]:
        if v is None:
            return None
        raw = str(v).strip()
        if raw in ("", "-", "N/A", "None", "null", "nan"):
            return None
        try:
            return float(raw)
        except (ValueError, TypeError):
            return None

    @field_validator("late_in_count", "early_out_count", mode="before")
    @classmethod
    def coerce_count(cls, v: Any) -> int:
        return _safe_int(v)

    # ── Derived properties ─────────────────────────────────

    @property
    def total_present(self) -> int:
        """Integer present days for DB storage (rounds 0.5 → 1)."""
        return round(self.present_days)

    @property
    def total_absent(self) -> int:
        return round(self.absent_days)

    @property
    def total_late(self) -> int:
        """Use late_in_count if available, else 0."""
        return self.late_in_count

    @property
    def total_half_day(self) -> int:
        """
        Estimate half-days from fractional present_days.
        A day that is 0.5 = half-day. Count = fractional part × 2.
        """
        fractional = self.present_days - int(self.present_days)
        return 1 if fractional == 0.5 else 0

    @property
    def total_leave(self) -> int:
        """Total leave = paid + unpaid + tour days."""
        return round(self.paid_leave_days + self.unpaid_leave_days + self.tour_days)

    @property
    def avg_work_hours_timedelta(self) -> Optional[timedelta]:
        """
        Compute average work hours as timedelta.

        Priority: ``work_hours_hhmm`` → ``work_hours_minutes``.
        """
        td = _parse_hhmm_to_timedelta(self.work_hours_hhmm)
        if td is not None:
            return td
        if self.work_hours_minutes is not None and self.work_hours_minutes > 0:
            return timedelta(minutes=self.work_hours_minutes)
        return None

    @property
    def avg_work_hours_interval_str(self) -> Optional[str]:
        """PostgreSQL-compatible INTERVAL string for ``avg_work_hrs`` column."""
        td = self.avg_work_hours_timedelta
        if td is None:
            return None
        total_secs = int(td.total_seconds())
        h, remainder = divmod(total_secs, 3600)
        m, s = divmod(remainder, 60)
        return f"{h} hours {m} minutes {s} seconds"


class MonthlySyncResult(BaseModel):
    """Summary of a monthly COSEC → database sync operation."""
    total_fetched: int = 0
    validated: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    error_messages: List[str] = Field(default_factory=list)
