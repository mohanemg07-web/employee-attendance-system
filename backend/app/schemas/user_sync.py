"""
Pydantic schemas for validating parsed Matrix COSEC User Master data.

These schemas match the pipe-delimited response from the COSEC API endpoint
``/api.svc/v2/user`` (see Matrix COSEC Web API User Guide, pp. 47–56).

Response is pipe-delimited text like the monthly attendance endpoint,
with tag names as the header row and ``<EOT>`` as the terminator.

Key tag names mapped here:
    id, reference-code, name, short-name, active, personal-email,
    official-email, department, designation, department-name,
    designation-name, organization, organization-name, branch,
    branch-name, section, section-name, category, category-name,
    grade, grade-name, reporting-incharge, rg_incharge_1,
    rg_incharge_2, joining-date, leaving-date, gender, full-name
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Tag-name mapping ───────────────────────────────────────
# Maps COSEC pipe-header tag names to our canonical schema field names.
# Multiple casing variants are mapped because the API can return either
# depending on the ``return-field-name`` parameter (0, 1, or 2).
USER_TAG_MAP: Dict[str, str] = {
    # Identity
    "id":                   "employee_code",
    "Id":                   "employee_code",
    "ID":                   "employee_code",
    "reference-code":       "reference_code",
    "name":                 "full_name",
    "Name":                 "full_name",
    "short-name":           "short_name",
    "full-name":            "full_name_extended",
    "Full Name":            "full_name_extended",

    # Status
    "active":               "active_status",
    "Active":               "active_status",

    # Contact
    "personal-email":       "personal_email",
    "official-email":       "official_email",
    "personal-phone":       "personal_phone",
    "personal-cell":        "personal_cell",
    "official-phone":       "official_phone",
    "official-cell":        "official_cell",

    # Organizational hierarchy IDs (numeric)
    "organization":         "organization_id",
    "branch":               "branch_id",
    "department":           "department_id",
    "designation":          "designation_id",
    "section":              "section_id",
    "category":             "category_id",
    "grade":                "grade_id",

    # Organizational hierarchy Names (strings)
    "organization-name":    "organization_name",
    "branch-name":          "branch_name",
    "department-name":      "department_name",
    "designation-name":     "designation_name",
    "section-name":         "section_name",
    "category-name":        "category_name",
    "grade-name":           "grade_name",

    # Organizational hierarchy Codes (alphanumeric)
    "organization_code":    "organization_code",
    "branch_code":          "branch_code",
    "department_code":      "department_code",
    "designation_code":     "designation_code",
    "section_code":         "section_code",
    "category_code":       "category_code",
    "grade_code":           "grade_code",

    # Reporting / Manager
    "reporting-incharge":   "reporting_incharge_id",
    "rg_id":                "reporting_group_id",
    "rg_name":              "reporting_group_name",
    "rg_incharge_1":        "reporting_incharge_1",
    "rg_incharge_2":        "reporting_incharge_2",

    # Dates
    "joining-date":         "joining_date_raw",
    "leaving-date":         "leaving_date_raw",
    "date-of-birth":        "date_of_birth_raw",
    "confirmation-date":    "confirmation_date_raw",

    # Demographics
    "gender":               "gender",
    "blood-group":          "blood_group",
    "marital-status":       "marital_status",
    "nationality":          "nationality",

    # Employment config
    "employment-profile":   "employment_profile",
    "employment-type":      "employment_type",
    "leave_group":          "leave_group",
}


def remap_user_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Translate raw COSEC tag names into canonical schema field names.

    Unmapped keys are preserved in ``raw_payload`` for auditing.
    """
    mapped: Dict[str, Any] = {}
    for key, value in raw.items():
        canonical = USER_TAG_MAP.get(key)
        if canonical:
            mapped[canonical] = value
    mapped["raw_payload"] = raw
    return mapped


# ── Helpers ────────────────────────────────────────────────

def _parse_ddmmyyyy(val: Any) -> Optional[date]:
    """
    Parse COSEC date format ``ddmmyyyy`` into a ``date`` object.

    Also handles ``dd/mm/yyyy`` and ``dd-mm-yyyy`` variants.
    Returns ``None`` for empty or invalid values.
    """
    if val is None:
        return None
    raw = str(val).strip()
    if raw in ("", "-", "N/A", "None", "null", "nan", "0"):
        return None

    # Try ddmmyyyy (8 digits, no separators)
    if re.match(r"^\d{8}$", raw):
        try:
            return datetime.strptime(raw, "%d%m%Y").date()
        except ValueError:
            return None

    # Try dd/mm/yyyy or dd-mm-yyyy
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue

    return None


def _safe_str(val: Any, default: str = "") -> str:
    """Coerce to stripped string, returning ``default`` on None."""
    if val is None:
        return default
    s = str(val).strip()
    return s if s else default


def _safe_int(val: Any, default: Optional[int] = None) -> Optional[int]:
    """Coerce to int or return ``default``."""
    if val is None:
        return default
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return default


# ── Main Schema ────────────────────────────────────────────

class UserMasterSyncSchema(BaseModel):
    """
    Validated representation of a single employee record from the
    Matrix COSEC User Master API.

    This schema normalises the COSEC pipe-delimited output into
    clean Python types suitable for upserting into the ``employees`` table.
    """

    # ── Identity ───────────────────────────────────────────
    employee_code: str = Field(
        ..., min_length=1,
        description="User ID / slot number from COSEC (tag: id).",
    )
    reference_code: Optional[str] = Field(
        default=None,
        description="Reference code (tag: reference-code). Up to 8 digits.",
    )
    full_name: str = Field(
        ..., min_length=1,
        description="User display name (tag: name). Max 45 chars.",
    )
    short_name: Optional[str] = Field(
        default=None,
        description="Short name (tag: short-name). Max 15 chars.",
    )
    full_name_extended: Optional[str] = Field(
        default=None,
        description="Full name (tag: full-name). Max 200 chars.",
    )

    # ── Status ─────────────────────────────────────────────
    active_status: str = Field(
        default="1",
        description="1=Active, 0=Inactive, 2=Inactive+Revoke (tag: active).",
    )

    # ── Contact ────────────────────────────────────────────
    personal_email: Optional[str] = Field(
        default=None,
        description="Personal email (tag: personal-email). Max 100 chars.",
    )
    official_email: Optional[str] = Field(
        default=None,
        description="Official email (tag: official-email). Max 100 chars.",
    )
    personal_phone: Optional[str] = Field(default=None)
    personal_cell: Optional[str] = Field(default=None)
    official_phone: Optional[str] = Field(default=None)
    official_cell: Optional[str] = Field(default=None)

    # ── Org hierarchy (IDs) ────────────────────────────────
    organization_id: Optional[str] = Field(default=None)
    branch_id: Optional[str] = Field(default=None)
    department_id: Optional[str] = Field(default=None)
    designation_id: Optional[str] = Field(default=None)
    section_id: Optional[str] = Field(default=None)
    category_id: Optional[str] = Field(default=None)
    grade_id: Optional[str] = Field(default=None)

    # ── Org hierarchy (Names) ──────────────────────────────
    organization_name: Optional[str] = Field(default=None)
    branch_name: Optional[str] = Field(default=None)
    department_name: Optional[str] = Field(
        default=None,
        description="Department name (tag: department-name).",
    )
    designation_name: Optional[str] = Field(
        default=None,
        description="Designation / role title (tag: designation-name).",
    )
    section_name: Optional[str] = Field(default=None)
    category_name: Optional[str] = Field(default=None)
    grade_name: Optional[str] = Field(default=None)

    # ── Org hierarchy (Codes) ──────────────────────────────
    organization_code: Optional[str] = Field(default=None)
    branch_code: Optional[str] = Field(default=None)
    department_code: Optional[str] = Field(default=None)
    designation_code: Optional[str] = Field(default=None)
    section_code: Optional[str] = Field(default=None)
    category_code: Optional[str] = Field(default=None)
    grade_code: Optional[str] = Field(default=None)

    # ── Reporting / Manager ────────────────────────────────
    reporting_incharge_id: Optional[str] = Field(
        default=None,
        description=(
            "Reporting In-Charge slot ID (tag: reporting-incharge). "
            "Range 1-9999. This maps to another employee_code for hierarchy."
        ),
    )
    reporting_group_id: Optional[str] = Field(default=None)
    reporting_group_name: Optional[str] = Field(default=None)
    reporting_incharge_1: Optional[str] = Field(
        default=None,
        description=(
            "Reporting Group Incharge 1's User ID (tag: rg_incharge_1). "
            "This is the *primary* manager code for adjacency list."
        ),
    )
    reporting_incharge_2: Optional[str] = Field(
        default=None,
        description="Reporting Group Incharge 2's User ID (tag: rg_incharge_2).",
    )

    # ── Dates ──────────────────────────────────────────────
    joining_date_raw: Optional[str] = Field(default=None)
    leaving_date_raw: Optional[str] = Field(default=None)
    date_of_birth_raw: Optional[str] = Field(default=None)
    confirmation_date_raw: Optional[str] = Field(default=None)

    # ── Demographics ───────────────────────────────────────
    gender: Optional[str] = Field(default=None)
    blood_group: Optional[str] = Field(default=None)
    marital_status: Optional[str] = Field(default=None)
    nationality: Optional[str] = Field(default=None)

    # ── Employment config ──────────────────────────────────
    employment_profile: Optional[str] = Field(default=None)
    employment_type: Optional[str] = Field(default=None)
    leave_group: Optional[str] = Field(default=None)

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

    @field_validator("full_name", mode="before")
    @classmethod
    def strip_full_name(cls, v: Any) -> str:
        s = _safe_str(v)
        return s if s else "UNKNOWN"

    @field_validator("active_status", mode="before")
    @classmethod
    def coerce_active(cls, v: Any) -> str:
        return _safe_str(v, "1")

    @field_validator(
        "personal_email", "official_email",
        mode="before",
    )
    @classmethod
    def clean_email(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip()
        if s in ("", "-", "N/A", "None", "null", "nan"):
            return None
        # Basic email sanity (must contain @)
        if "@" not in s:
            return None
        return s

    # ── Model-level validator: name fallback ───────────────
    @model_validator(mode="after")
    def _apply_name_fallback(self) -> "UserMasterSyncSchema":
        """
        If ``full_name`` is the default 'UNKNOWN' but ``full_name_extended``
        has a real value, use that instead.  This handles cases where the
        API returns the name only in the ``full-name`` tag.
        """
        if self.full_name == "UNKNOWN" and self.full_name_extended:
            ext = self.full_name_extended.strip()
            if ext and ext not in ("", "-", "N/A"):
                self.full_name = ext
        return self

    # ── Derived properties ─────────────────────────────────

    @property
    def is_active(self) -> bool:
        """True when ``active_status`` == '1'."""
        return self.active_status == "1"

    @property
    def best_email(self) -> Optional[str]:
        """
        Return the best available email:
        official_email → personal_email → None.
        """
        return self.official_email or self.personal_email

    @property
    def department_display(self) -> Optional[str]:
        """Department name for the ``employees.department`` column."""
        return self.department_name or self.department_id

    @property
    def designation_display(self) -> Optional[str]:
        """Designation name for role inference."""
        return self.designation_name or self.designation_id

    @property
    def manager_code(self) -> Optional[str]:
        """
        Best available manager employee_code for the adjacency list.

        Priority:
            1. ``reporting_incharge_1`` (reporting group incharge 1)
            2. ``reporting_incharge_id`` (reporting-incharge)
            3. ``reporting_incharge_2`` (fallback)

        Returns ``None`` if no manager is assigned or the value is
        empty/self-referencing.
        """
        for candidate in (
            self.reporting_incharge_1,
            self.reporting_incharge_id,
            self.reporting_incharge_2,
        ):
            if candidate is not None:
                code = str(candidate).strip()
                if code and code not in ("", "0", "-", "N/A"):
                    # Prevent self-reference
                    if code != self.employee_code:
                        return code
        return None

    @property
    def joining_date(self) -> Optional[date]:
        return _parse_ddmmyyyy(self.joining_date_raw)

    @property
    def leaving_date(self) -> Optional[date]:
        return _parse_ddmmyyyy(self.leaving_date_raw)

    @property
    def date_of_birth(self) -> Optional[date]:
        """Parsed date-of-birth from raw COSEC format."""
        return _parse_ddmmyyyy(self.date_of_birth_raw)

    @property
    def inferred_role(self) -> str:
        """
        Infer the application-level role from COSEC data.

        Heuristic:
        - Users who are someone else's ``reporting_incharge_1`` → MANAGER
          (resolved externally during batch processing)
        - Default → EMPLOYEE
        """
        return "EMPLOYEE"

    def __repr__(self) -> str:
        return (
            f"<UserMasterSync code={self.employee_code!r} "
            f"name={self.full_name!r} "
            f"active={self.active_status} "
            f"mgr={self.manager_code!r}>"
        )


class UserSyncResult(BaseModel):
    """Summary of a COSEC User Master → database sync operation."""
    total_fetched: int = 0
    validated: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    manager_links_set: int = 0
    manager_links_failed: int = 0
    errors: int = 0
    error_messages: List[str] = Field(default_factory=list)
