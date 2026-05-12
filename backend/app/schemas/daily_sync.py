"""
Pydantic schemas for validating parsed Matrix COSEC Daily Attendance data.

These schemas match the pipe-delimited response from the COSEC API endpoint
``/api.svc/v2/attendance-daily`` (see Matrix COSEC Web API User Guide,
pp. 96–105).

Response is pipe-delimited text with tag names as the header row and
``<EOT>`` as the terminator.

Key tag names mapped here (from PDF response fields table):
    USERID, USERNAME, PROCESSDATE, PUNCH1, PUNCH2,
    WORKTIME, WORKTIME_HHMM, LATEIN, LATEIN_HHMM,
    EARLYOUT, EARLYOUT_HHMM, OVERTIME, OVERTIME_HHMM,
    FIRSTHALF, SECONDHALF, DAYSTATUS, NETWORKHRS,
    SHIFTSTART, SHIFTEND, WEEKOFFANDHOLIDAY, SUMMARY
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Timezone constant ──────────────────────────────────────
IST = timezone(timedelta(hours=5, minutes=30))


# ── Canonical Status Enum ──────────────────────────────────

class AttendanceStatus(str, Enum):
    """Canonical attendance status values used across the system."""
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    LATE = "LATE"
    HALF_DAY = "HALF_DAY"
    WEEKEND = "WEEKEND"
    ON_LEAVE = "ON_LEAVE"
    HOLIDAY = "HOLIDAY"


# Mapping of raw COSEC status / half-status codes → canonical enum
_STATUS_ALIAS_MAP: Dict[str, AttendanceStatus] = {
    # Direct status strings
    "present": AttendanceStatus.PRESENT,
    "p": AttendanceStatus.PRESENT,
    "pr": AttendanceStatus.PRESENT,
    "absent": AttendanceStatus.ABSENT,
    "a": AttendanceStatus.ABSENT,
    "ab": AttendanceStatus.ABSENT,
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
    "ph": AttendanceStatus.HOLIDAY,
    # DAYSTATUS numeric codes (from PDF p. 101)
    "0": AttendanceStatus.WEEKEND,      # WO
    "1": AttendanceStatus.HOLIDAY,      # PH
    "2": AttendanceStatus.WEEKEND,      # WO/PH
    "3": AttendanceStatus.PRESENT,      # Normal
    # FIRSTHALF / SECONDHALF codes (from PDF p. 100)
    "wo": AttendanceStatus.WEEKEND,
    "fb": AttendanceStatus.PRESENT,     # Field Break
    "rd": AttendanceStatus.WEEKEND,     # Rest Day
    "in": AttendanceStatus.PRESENT,     # Official In
}


# ── Tag-name mapping ───────────────────────────────────────
# Maps COSEC pipe-header tag names to our canonical schema field names.
# Multiple casing variants are handled for robustness.
DAILY_TAG_MAP: Dict[str, str] = {
    # Identity
    "USERID":              "employee_code",
    "UserID":              "employee_code",
    "userid":              "employee_code",
    "USERNAME":            "employee_name",
    "UserName":            "employee_name",
    "username":            "employee_name",
    "USER NAME":           "employee_name",
    "short_name":          "short_name",

    # Date
    "PROCESSDATE":         "process_date",
    "ProcessDate":         "process_date",
    "processdate":         "process_date",
    "PROCESSDATE_D":       "process_date_dt",

    # Punches (first-in / last-out from Punch1 / Punch2)
    "PUNCH1":              "punch1",
    "Punch1":              "punch1",
    "punch1":              "punch1",
    "PUNCH1_DATE":         "punch1_date",
    "PUNCH1_TIME":         "punch1_time",
    "PUNCH2":              "punch2",
    "Punch2":              "punch2",
    "punch2":              "punch2",
    "PUNCH2_DATE":         "punch2_date",
    "PUNCH2_TIME":         "punch2_time",

    # Out punch (last out)
    "OUTPUNCH":            "out_punch",
    "OUTPUNCH_DATE":       "out_punch_date",
    "OUTPUNCH_TIME":       "out_punch_time",

    # Work time
    "WORKTIME":            "work_time_minutes",
    "WorkTime":            "work_time_minutes",
    "worktime":            "work_time_minutes",
    "WORKTIME_HHMM":       "work_time_hhmm",
    "WorkTime_HHMM":       "work_time_hhmm",

    # Net work hours
    "NETWORKHRS":          "net_work_hhmm",
    "NetworkHrs":          "net_work_hhmm",

    # Overtime
    "OVERTIME":            "overtime_minutes",
    "Overtime":            "overtime_minutes",
    "overtime":            "overtime_minutes",
    "OVERTIME_HHMM":       "overtime_hhmm",

    # Late-in
    "LATEIN":              "late_in_minutes",
    "LateIn":              "late_in_minutes",
    "latein":              "late_in_minutes",
    "LATEIN_HHMM":         "late_in_hhmm",

    # Early-out
    "EARLYOUT":            "early_out_minutes",
    "EarlyOut":            "early_out_minutes",
    "EARLY OUT":           "early_out_minutes",
    "earlyout":            "early_out_minutes",
    "EARLYOUT_HHMM":       "early_out_hhmm",

    # Half-day status
    "FIRSTHALF":           "first_half_status",
    "firsthalf":           "first_half_status",
    "SECONDHALF":          "second_half_status",
    "secondhalf":          "second_half_status",

    # Day status (0=WO, 1=PH, 2=WO/PH, 3=Normal)
    "DAYSTATUS":           "day_status",
    "DayStatus":           "day_status",
    "daystatus":           "day_status",

    # Weekend / holiday flag
    "WEEKOFFANDHOLIDAY":   "weekoff_and_holiday",

    # Shift
    "WORKINGSHIFT":        "working_shift",
    "WorkingShift":        "working_shift",
    "SCHEDULESHIFT":       "schedule_shift",
    "SHIFTSTART":          "shift_start",
    "SHIFTEND":            "shift_end",
    "SHIFTTYPE":           "shift_type",

    # Summary text
    "SUMMARY":             "summary",
    "Summary":             "summary",

    # Reference
    "ADLUSERID":           "reference_no",
    "integration_reference": "integration_reference",

    # Org hierarchy
    "ORGID":               "org_id",
    "BRCID":               "branch_id",
    "DPTID":               "department_id",
    "DSGID":               "designation_id",
    "SECID":               "section_id",
    "CTGID":               "category_id",
    "GRDID":               "grade_id",
    "GENDER":              "gender",

    # Names
    "organization_name":   "organization_name",
    "branch_name":         "branch_name",
    "department_name":     "department_name",
    "designation_name":    "designation_name",
    "section_name":        "section_name",
    "category_name":       "category_name",
    "grade_name":          "grade_name",
    "full-name":           "full_name",
}


def remap_daily_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Translate raw COSEC tag names into canonical schema field names.

    Unmapped keys are preserved in ``raw_payload`` for auditing.
    """
    mapped: Dict[str, Any] = {}
    for key, value in raw.items():
        canonical = DAILY_TAG_MAP.get(key)
        if canonical:
            mapped[canonical] = value
    mapped["raw_payload"] = raw
    return mapped


# ── Helpers ────────────────────────────────────────────────

def _parse_date(val: Any) -> Optional[date]:
    """
    Parse COSEC date from multiple formats:
    ``dd/mm/yyyy``, ``ddmmyyyy``, ``yyyy-mm-dd``, ``mm/dd/yyyy``.
    Returns ``None`` for empty or invalid values.
    """
    if val is None:
        return None
    if isinstance(val, date):
        return val
    if isinstance(val, datetime):
        return val.date()

    raw = str(val).strip()
    if raw in ("", "-", "N/A", "None", "null", "nan", "0"):
        return None

    for fmt in ("%d/%m/%Y", "%d%m%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_punch_datetime(
    val: Any,
    fallback_date: Optional[date] = None,
) -> Optional[datetime]:
    """
    Parse a punch timestamp from COSEC formats:
    - ``dd/mm/yyyy HH:MM`` (PUNCH1/PUNCH2 combined)
    - ``mm/dd/yyyy HH:MM`` (OUTPUNCH format from PDF)
    - ``HH:MM`` (time only — combined with ``fallback_date``)
    - Full ISO datetime strings

    Returns timezone-aware (IST) datetime or ``None``.
    """
    if val is None:
        return None

    raw = str(val).strip()
    if raw in ("", "-", "N/A", "None", "null", "nan"):
        return None

    if isinstance(val, datetime):
        return val.replace(tzinfo=IST) if val.tzinfo is None else val

    # Try full timestamp formats (dd/mm/yyyy HH:MM from PDF)
    for fmt in (
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    ):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.replace(tzinfo=IST) if dt.tzinfo is None else dt
        except ValueError:
            continue

    # Time-only: "HH:MM" or "HH:MM:SS"
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M:%S %p", "%I:%M %p"):
        try:
            t = datetime.strptime(raw, fmt).time()
            if fallback_date:
                return datetime.combine(fallback_date, t, tzinfo=IST)
            # Use sentinel date; model_validator will fix later
            return datetime.combine(date(1970, 1, 1), t, tzinfo=IST)
        except ValueError:
            continue

    return None


def _parse_hhmm_to_timedelta(val: Any) -> Optional[timedelta]:
    """
    Parse ``HH:MM``, ``HHH:MM``, or ``HHHHHH:MM`` formatted string
    into a ``timedelta``. Returns ``None`` for empty/invalid values.
    """
    if val is None:
        return None
    raw = str(val).strip()
    if raw in ("", "-", "N/A", "None", "null", "nan", "0", "000:00", "00:00"):
        return None
    match = re.match(r"^(\d+):(\d{2})(?::(\d{2}))?$", raw)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        seconds = int(match.group(3) or 0)
        return timedelta(hours=hours, minutes=minutes, seconds=seconds)
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


def _safe_str(val: Any, default: str = "") -> str:
    """Coerce to stripped string, returning ``default`` on None."""
    if val is None:
        return default
    s = str(val).strip()
    return s if s else default


# ── Main Schema ────────────────────────────────────────────

class DailyAttendanceSyncSchema(BaseModel):
    """
    Validated representation of a single daily attendance record
    from the Matrix COSEC API.

    This schema normalises the COSEC pipe-delimited output into
    clean Python types suitable for upserting into ``attendance_logs``.
    """

    # ── Identity ───────────────────────────────────────────
    employee_code: str = Field(
        ..., min_length=1,
        description="User ID from COSEC (tag: USERID). Max 15 chars.",
    )
    employee_name: Optional[str] = Field(
        default=None,
        description="User display name (tag: USERNAME). Max 45 chars.",
    )
    short_name: Optional[str] = Field(default=None)

    # ── Date ───────────────────────────────────────────────
    process_date: Optional[str] = Field(
        default=None,
        description="Process date string (tag: PROCESSDATE). dd/mm/yyyy.",
    )
    process_date_dt: Optional[str] = Field(
        default=None,
        description="Process date+time (tag: PROCESSDATE_D). mm/dd/yy HH:MM:SS.",
    )

    # ── Punches ────────────────────────────────────────────
    punch1: Optional[str] = Field(
        default=None,
        description="First punch (tag: PUNCH1). dd/mm/yyyy HH:MM.",
    )
    punch1_date: Optional[str] = Field(default=None)
    punch1_time: Optional[str] = Field(default=None)
    punch2: Optional[str] = Field(
        default=None,
        description="Second punch (tag: PUNCH2). dd/mm/yyyy HH:MM.",
    )
    punch2_date: Optional[str] = Field(default=None)
    punch2_time: Optional[str] = Field(default=None)

    # Out punch (last known out)
    out_punch: Optional[str] = Field(default=None)
    out_punch_date: Optional[str] = Field(default=None)
    out_punch_time: Optional[str] = Field(default=None)

    # ── Work time ──────────────────────────────────────────
    work_time_minutes: Optional[str] = Field(
        default=None,
        description="Total work time in minutes (tag: WORKTIME).",
    )
    work_time_hhmm: Optional[str] = Field(
        default=None,
        description="Total work time as HH:MM (tag: WORKTIME_HHMM).",
    )
    net_work_hhmm: Optional[str] = Field(
        default=None,
        description="Net work hours as HHHHHH:MM (tag: NETWORKHRS).",
    )

    # ── Overtime / Late / Early ────────────────────────────
    overtime_minutes: Optional[str] = Field(default=None)
    overtime_hhmm: Optional[str] = Field(default=None)
    late_in_minutes: Optional[str] = Field(default=None)
    late_in_hhmm: Optional[str] = Field(default=None)
    early_out_minutes: Optional[str] = Field(default=None)
    early_out_hhmm: Optional[str] = Field(default=None)

    # ── Half-day / Day status ──────────────────────────────
    first_half_status: Optional[str] = Field(
        default=None,
        description="First half status (tag: FIRSTHALF). PR/AB/WO/PH/etc.",
    )
    second_half_status: Optional[str] = Field(
        default=None,
        description="Second half status (tag: SECONDHALF). PR/AB/WO/PH/etc.",
    )
    day_status: Optional[str] = Field(
        default=None,
        description="Day status code (tag: DAYSTATUS). 0=WO, 1=PH, 2=WO/PH, 3=Normal.",
    )
    weekoff_and_holiday: Optional[str] = Field(default=None)

    # ── Shift ──────────────────────────────────────────────
    working_shift: Optional[str] = Field(default=None)
    schedule_shift: Optional[str] = Field(default=None)
    shift_start: Optional[str] = Field(default=None)
    shift_end: Optional[str] = Field(default=None)
    shift_type: Optional[str] = Field(default=None)

    # ── Summary ────────────────────────────────────────────
    summary: Optional[str] = Field(
        default=None,
        description="Summary text (tag: SUMMARY). Max 50 chars.",
    )

    # ── References / Org ───────────────────────────────────
    reference_no: Optional[str] = Field(default=None)
    integration_reference: Optional[str] = Field(default=None)
    org_id: Optional[str] = Field(default=None)
    branch_id: Optional[str] = Field(default=None)
    department_id: Optional[str] = Field(default=None)
    designation_id: Optional[str] = Field(default=None)
    section_id: Optional[str] = Field(default=None)
    category_id: Optional[str] = Field(default=None)
    grade_id: Optional[str] = Field(default=None)
    gender: Optional[str] = Field(default=None)

    # Names
    organization_name: Optional[str] = Field(default=None)
    branch_name: Optional[str] = Field(default=None)
    department_name: Optional[str] = Field(default=None)
    designation_name: Optional[str] = Field(default=None)
    section_name: Optional[str] = Field(default=None)
    category_name: Optional[str] = Field(default=None)
    grade_name: Optional[str] = Field(default=None)
    full_name: Optional[str] = Field(default=None)

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

    # ── Derived properties ─────────────────────────────────

    @property
    def log_date(self) -> Optional[date]:
        """
        Parse the attendance date from available date fields.

        Priority: ``process_date`` → ``punch1_date`` → ``punch1`` date part.
        """
        # Try process_date first (dd/mm/yyyy)
        d = _parse_date(self.process_date)
        if d:
            return d

        # Try punch1_date
        d = _parse_date(self.punch1_date)
        if d:
            return d

        # Try extracting date from punch1 (dd/mm/yyyy HH:MM)
        if self.punch1:
            dt = _parse_punch_datetime(self.punch1)
            if dt and dt.date() != date(1970, 1, 1):
                return dt.date()

        return None

    @property
    def first_in(self) -> Optional[datetime]:
        """
        Parse the first punch-in timestamp.

        Priority: ``punch1`` → ``punch1_time`` + ``log_date``.
        """
        log_d = self.log_date

        # Try combined punch1 (dd/mm/yyyy HH:MM)
        dt = _parse_punch_datetime(self.punch1, fallback_date=log_d)
        if dt:
            # Fix sentinel date
            if dt.date() == date(1970, 1, 1) and log_d:
                dt = datetime.combine(log_d, dt.time(), tzinfo=IST)
            return dt

        # Try time-only from punch1_time
        if self.punch1_time:
            dt = _parse_punch_datetime(self.punch1_time, fallback_date=log_d)
            if dt:
                if dt.date() == date(1970, 1, 1) and log_d:
                    dt = datetime.combine(log_d, dt.time(), tzinfo=IST)
                return dt

        return None

    @property
    def last_out(self) -> Optional[datetime]:
        """
        Parse the last punch-out timestamp.

        Priority: ``out_punch`` → ``punch2`` → ``out_punch_time`` + ``log_date``.
        """
        log_d = self.log_date

        # Try out_punch first (mm/dd/yyyy HH:MM per PDF)
        dt = _parse_punch_datetime(self.out_punch, fallback_date=log_d)
        if dt:
            if dt.date() == date(1970, 1, 1) and log_d:
                dt = datetime.combine(log_d, dt.time(), tzinfo=IST)
            return dt

        # Try punch2
        dt = _parse_punch_datetime(self.punch2, fallback_date=log_d)
        if dt:
            if dt.date() == date(1970, 1, 1) and log_d:
                dt = datetime.combine(log_d, dt.time(), tzinfo=IST)
            return dt

        # Try time-only from out_punch_time or punch2_time
        for time_field in (self.out_punch_time, self.punch2_time):
            if time_field:
                dt = _parse_punch_datetime(time_field, fallback_date=log_d)
                if dt:
                    if dt.date() == date(1970, 1, 1) and log_d:
                        dt = datetime.combine(log_d, dt.time(), tzinfo=IST)
                    return dt

        return None

    @property
    def gross_work_hrs(self) -> Optional[timedelta]:
        """
        Compute gross work hours.

        Priority: ``work_time_hhmm`` → ``work_time_minutes`` →
        computed from ``first_in``/``last_out``.
        """
        # Try HH:MM format first
        td = _parse_hhmm_to_timedelta(self.work_time_hhmm)
        if td is not None:
            return td

        # Try minutes
        if self.work_time_minutes is not None:
            mins = _safe_float(self.work_time_minutes)
            if mins > 0:
                return timedelta(minutes=mins)

        # Compute from punches
        fi = self.first_in
        lo = self.last_out
        if fi and lo and lo > fi:
            return lo - fi

        return None

    @property
    def net_work_hrs(self) -> Optional[timedelta]:
        """Net work hours from NETWORKHRS tag."""
        return _parse_hhmm_to_timedelta(self.net_work_hhmm)

    @property
    def gross_work_hrs_interval_str(self) -> Optional[str]:
        """PostgreSQL-compatible INTERVAL string for ``gross_work_hrs`` column."""
        td = self.gross_work_hrs
        if td is None:
            return None
        total_secs = int(td.total_seconds())
        h, remainder = divmod(total_secs, 3600)
        m, s = divmod(remainder, 60)
        return f"{h} hours {m} minutes {s} seconds"

    @property
    def net_work_hrs_interval_str(self) -> Optional[str]:
        """PostgreSQL-compatible INTERVAL string for ``net_work_hrs`` column."""
        td = self.net_work_hrs
        if td is None:
            return None
        total_secs = int(td.total_seconds())
        h, remainder = divmod(total_secs, 3600)
        m, s = divmod(remainder, 60)
        return f"{h} hours {m} minutes {s} seconds"

    @property
    def status(self) -> AttendanceStatus:
        """
        Derive canonical attendance status from COSEC fields.

        Resolution order:
        1. ``day_status`` (0=WO, 1=PH, 2=WO/PH, 3=Normal)
        2. ``weekoff_and_holiday`` (1=WO/PH)
        3. ``first_half_status`` / ``second_half_status`` (PR/AB/WO/PH)
        4. Presence of punches → PRESENT or ABSENT
        5. ``late_in_minutes`` > 0 → LATE
        """
        # Day status code
        if self.day_status is not None:
            ds = str(self.day_status).strip()
            if ds in ("0", "2"):
                return AttendanceStatus.WEEKEND
            if ds == "1":
                return AttendanceStatus.HOLIDAY

        # Weekoff/holiday flag
        if self.weekoff_and_holiday is not None:
            if str(self.weekoff_and_holiday).strip() == "1":
                return AttendanceStatus.WEEKEND

        # Half-day status codes
        fh = _safe_str(self.first_half_status).lower()
        sh = _safe_str(self.second_half_status).lower()

        if fh and sh:
            fh_stat = _STATUS_ALIAS_MAP.get(fh)
            sh_stat = _STATUS_ALIAS_MAP.get(sh)

            if fh in ("wo",) and sh in ("wo",):
                return AttendanceStatus.WEEKEND
            if fh in ("ph",) and sh in ("ph",):
                return AttendanceStatus.HOLIDAY
            if fh in ("ab",) and sh in ("ab",):
                return AttendanceStatus.ABSENT
            # One half present, one absent → HALF_DAY
            if (fh in ("pr", "in") and sh in ("ab",)) or \
               (fh in ("ab",) and sh in ("pr", "in")):
                return AttendanceStatus.HALF_DAY
            # Both present
            if fh in ("pr", "in") and sh in ("pr", "in"):
                # Check for late-in
                late = _safe_float(self.late_in_minutes)
                if late > 0:
                    return AttendanceStatus.LATE
                return AttendanceStatus.PRESENT
            # Leave codes
            if fh_stat == AttendanceStatus.ON_LEAVE or \
               sh_stat == AttendanceStatus.ON_LEAVE:
                return AttendanceStatus.ON_LEAVE

        # Fallback: check punches
        if self.first_in is not None:
            late = _safe_float(self.late_in_minutes)
            if late > 0:
                return AttendanceStatus.LATE
            return AttendanceStatus.PRESENT

        return AttendanceStatus.ABSENT

    def __repr__(self) -> str:
        return (
            f"<DailyAttendanceSync code={self.employee_code!r} "
            f"date={self.log_date} status={self.status.value}>"
        )


class DailySyncResult(BaseModel):
    """Summary of a daily COSEC → database sync operation."""
    total_fetched: int = 0
    validated: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    error_messages: List[str] = Field(default_factory=list)
