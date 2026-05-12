"""
Matrix COSEC Web API client — LEGACY monolith (DEPRECATED).

.. deprecated:: 2026-04-29
    This module is superseded by three dedicated, production-hardened services:

    * ``app.services.matrix_user_master``  — User Master API
    * ``app.services.matrix_daily``        — Daily Attendance API
    * ``app.services.matrix_monthly``      — Monthly Attendance API

    Import via the unified facade:
    ``from app.services.matrix_sync import user_master_service, daily_attendance_service, monthly_service``

    This module is retained for backward compatibility but will not
    receive new features. Prefer the dedicated services for all new code.

Original Responsibilities (now split across dedicated modules)
───────────────────────────────────────────────────────────────
• POST-based Daily Attendance fetch with Basic Auth.
• Robust XML *and* JSON response parsing (auto-detected).
• Pydantic validation of every parsed record before DB insertion.
• Upsert into ``attendance_logs`` with provenance protection:
  records whose ``data_source == 'MANUAL_CSV'`` are **never** overwritten.
• Redis-backed live-attendance cache with configurable TTL.
• Structured ``logging`` throughout — no ``print()`` calls.

Environment variables consumed (via ``app.config.Settings``):
    MATRIX_COSEC_BASE_URL, MATRIX_COSEC_USERNAME, MATRIX_COSEC_PASSWORD,
    REDIS_URL, LIVE_CACHE_TTL_MINUTES
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree

import httpx
import redis.asyncio as aioredis
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.schemas.cosec import (
    AttendanceStatus,
    CosecDailyAttendanceRecord,
    CosecSyncResult,
    IST,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# ── XML field → Pydantic field mapping ──────────────────────
# Maps known COSEC XML/JSON keys to CosecDailyAttendanceRecord fields.
_FIELD_MAP: Dict[str, str] = {
    "user-id": "employee_code",
    "User-ID": "employee_code",
    "Employee-ID": "employee_code",
    "employee-id": "employee_code",
    "employee_code": "employee_code",
    "EmployeeCode": "employee_code",
    "date": "log_date",
    "Date": "log_date",
    "attendance-date": "log_date",
    "Attendance-Date": "log_date",
    "first-in": "first_in",
    "First-In": "first_in",
    "Punch1": "first_in",
    "first_in": "first_in",
    "FirstIn": "first_in",
    "last-out": "last_out",
    "Last-Out": "last_out",
    "Punch2": "last_out",
    "last_out": "last_out",
    "LastOut": "last_out",
    "gross-work-hrs": "work_hours",
    "Gross-Work-Hrs": "work_hours",
    "Work_Hours": "work_hours",
    "work-hours": "work_hours",
    "WorkHours": "work_hours",
    "total-hours": "work_hours",
    "status": "status",
    "Status": "status",
    "attendance-status": "status",
}


def _remap_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Translate raw API field names into canonical Pydantic field names."""
    mapped: Dict[str, Any] = {}
    for key, value in raw.items():
        canonical = _FIELD_MAP.get(key)
        if canonical:
            mapped[canonical] = value
        # Keep unmapped keys in raw_payload
    mapped["raw_payload"] = raw
    return mapped


class MatrixCosecService:
    """
    Asynchronous service class encapsulating all Matrix COSEC API interactions,
    response parsing, validation, and database upsert logic.

    Usage::

        service = MatrixCosecService()
        records = await service.fetch_daily_attendance("01/04/2026", "30/04/2026")
        result  = await service.sync_to_database(db_session, records)
    """

    # ── Construction ───────────────────────────────────────

    def __init__(self) -> None:
        self.base_url: str = settings.MATRIX_COSEC_BASE_URL.rstrip("/")
        self.username: str = settings.MATRIX_COSEC_USERNAME
        self.password: str = settings.MATRIX_COSEC_PASSWORD
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        """Lazy-initialise the async Redis connection."""
        if self._redis is None:
            self._redis = aioredis.from_url(
                settings.REDIS_URL, decode_responses=True
            )
        return self._redis

    # ── API Communication ──────────────────────────────────

    async def fetch_daily_attendance(
        self,
        start_date: str,
        end_date: str,
        employee_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch Daily Attendance data from the COSEC Web API.

        Args:
            start_date: Start date in ``DD/MM/YYYY`` or ``YYYY-MM-DD`` format.
            end_date:   End date in the same format.
            employee_id: Optional employee / user ID.  When ``None`` all
                         employees are fetched.

        Returns:
            A list of raw record dicts parsed from the XML/JSON response,
            or an empty list on any failure (timeout, HTTP error, parse error).
        """
        url = f"{self.base_url}/api.svc/v2/attendance-daily"

        payload: Dict[str, Any] = {
            "Start-Date": start_date,
            "End-Date": end_date,
        }
        if employee_id:
            payload["Employee-ID"] = employee_id

        return await self._post(url, payload)

    async def fetch_monthly_attendance(
        self,
        month_year: str,
        employee_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch monthly attendance summary from the COSEC Web API.

        Args:
            month_year: Month-year string in ``MMYYYY`` format.
            employee_id: Optional filter by employee.

        Returns:
            Parsed records or empty list on failure.
        """
        url = f"{self.base_url}/api.svc/v2/attendance-monthly"
        payload: Dict[str, Any] = {"month-year": month_year}
        if employee_id:
            payload["Employee-ID"] = employee_id
        return await self._post(url, payload)

    async def fetch_user_list(self) -> List[Dict[str, Any]]:
        """Fetch the full user/employee list from the COSEC Web API."""
        url = f"{self.base_url}/api.svc/v2/user"
        return await self._post(url, {"action": "get"})

    # ── Internal HTTP helper ───────────────────────────────

    async def _post(
        self,
        url: str,
        payload: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Execute an authenticated POST request and parse the response.

        Handles ``httpx.TimeoutException`` and ``httpx.HTTPStatusError``
        gracefully by logging and returning an empty list so callers can
        fall back to the local database.
        """
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0),
            ) as client:
                response = await client.post(
                    url,
                    auth=(self.username, self.password),
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/xml, application/json",
                    },
                )
                response.raise_for_status()
                return self._auto_parse_response(response)

        except httpx.TimeoutException:
            logger.error(
                "COSEC API timeout: POST %s (connect/read exceeded)", url
            )
            return []

        except httpx.HTTPStatusError as exc:
            logger.error(
                "COSEC API HTTP %d: POST %s — %s",
                exc.response.status_code,
                url,
                exc.response.text[:500],
            )
            return []

        except httpx.RequestError as exc:
            logger.error("COSEC API connection error: %s — %s", url, exc)
            return []

        except Exception:
            logger.exception("Unexpected error calling COSEC API: POST %s", url)
            return []

    # ── Response Parsing (XML + JSON) ──────────────────────

    def _auto_parse_response(
        self, response: httpx.Response
    ) -> List[Dict[str, Any]]:
        """
        Auto-detect content type and delegate to the appropriate parser.

        Falls back to XML parsing if the Content-Type header is absent or
        ambiguous, since COSEC historically uses XML.
        """
        content_type = response.headers.get("content-type", "")
        body = response.text.strip()

        if not body:
            logger.warning("COSEC API returned an empty response body.")
            return []

        if "json" in content_type or body.startswith(("{", "[")):
            return self._parse_json_response(body)
        else:
            return self._parse_xml_response(body)

    @staticmethod
    def _parse_xml_response(raw_xml: str) -> List[Dict[str, Any]]:
        """
        Parse a COSEC XML response into a flat list of record dicts.

        The COSEC API typically returns structures like::

            <attendance-daily>
              <row>
                <user-id>EMP001</user-id>
                <date>01/04/2026</date>
                ...
              </row>
            </attendance-daily>

        Deeply nested elements are flattened by joining tag names with ``/``.
        """
        records: List[Dict[str, Any]] = []
        try:
            root = ElementTree.fromstring(raw_xml)
            for row in root.iter("row"):
                record: Dict[str, Any] = {}
                for child in row:
                    if len(child) > 0:
                        # Nested element — flatten
                        for sub in child:
                            key = f"{child.tag}/{sub.tag}"
                            record[key] = sub.text
                    else:
                        record[child.tag] = child.text
                if record:
                    records.append(record)
        except ElementTree.ParseError as exc:
            logger.error("Failed to parse COSEC XML response: %s", exc)
        return records

    @staticmethod
    def _parse_json_response(raw_json: str) -> List[Dict[str, Any]]:
        """
        Parse a COSEC JSON response into a flat list of record dicts.

        Handles both top-level arrays and nested structures like::

            {"attendance-daily": {"row": [...]}}
        """
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse COSEC JSON response: %s", exc)
            return []

        # Top-level list
        if isinstance(data, list):
            return data

        # Nested under a known wrapper key
        if isinstance(data, dict):
            for wrapper_key in (
                "attendance-daily",
                "attendance-monthly",
                "rows",
                "data",
                "result",
            ):
                nested = data.get(wrapper_key)
                if nested is not None:
                    rows = nested.get("row") if isinstance(nested, dict) else nested
                    if isinstance(rows, list):
                        return rows
                    if isinstance(rows, dict):
                        return [rows]
            # Fallback: treat the whole dict as a single record
            return [data]

        return []

    # ── Record Validation ──────────────────────────────────

    def validate_records(
        self, raw_records: List[Dict[str, Any]]
    ) -> List[CosecDailyAttendanceRecord]:
        """
        Validate and normalise a batch of raw record dicts through the
        ``CosecDailyAttendanceRecord`` Pydantic schema.

        Invalid records are logged and skipped (fail-safe).

        Args:
            raw_records: Flat dicts from :meth:`_parse_xml_response` or
                         :meth:`_parse_json_response`.

        Returns:
            List of validated ``CosecDailyAttendanceRecord`` instances.
        """
        validated: List[CosecDailyAttendanceRecord] = []
        for idx, raw in enumerate(raw_records):
            try:
                mapped = _remap_record(raw)
                record = CosecDailyAttendanceRecord(**mapped)
                validated.append(record)
            except ValidationError as exc:
                logger.warning(
                    "Skipping invalid COSEC record #%d: %s — raw=%s",
                    idx,
                    exc.errors(),
                    raw,
                )
        return validated

    # ── Database Upsert ────────────────────────────────────

    async def upsert_daily_record(
        self,
        db: AsyncSession,
        record: CosecDailyAttendanceRecord,
        source: str = "API",
        skip_manual: bool = True,
    ) -> str:
        """
        Upsert a single validated daily attendance record into
        ``attendance_logs``.

        **Provenance rule:** If ``skip_manual`` is ``True`` and the existing
        DB row has ``data_source == 'MANUAL_CSV'``, the row is **not**
        overwritten. This preserves manually-corrected data.

        Args:
            db: Active async SQLAlchemy session.
            record: Validated ``CosecDailyAttendanceRecord``.
            source: Data source tag (default ``"API"``).
            skip_manual: When ``True``, protect MANUAL_CSV records.

        Returns:
            One of ``"inserted"``, ``"updated"``, or ``"skipped"``.
        """
        # ── Resolve employee_id ────────────────────────────
        emp_result = await db.execute(
            text("SELECT id FROM employees WHERE employee_code = :code"),
            {"code": record.employee_code},
        )
        emp_row = emp_result.fetchone()
        if not emp_row:
            logger.debug(
                "Employee code '%s' not found in DB — skipping.",
                record.employee_code,
            )
            return "skipped"

        employee_id: int = emp_row[0]

        # ── Check existing record provenance ───────────────
        existing = await db.execute(
            text(
                "SELECT id, data_source FROM attendance_logs "
                "WHERE employee_id = :eid AND log_date = :ld"
            ),
            {"eid": employee_id, "ld": record.log_date},
        )
        existing_row = existing.fetchone()

        if existing_row:
            if skip_manual and existing_row[1] == "MANUAL_CSV":
                logger.debug(
                    "Skipping employee %s on %s — protected MANUAL_CSV record.",
                    record.employee_code,
                    record.log_date,
                )
                return "skipped"

        # ── Serialise fields for SQL ───────────────────────
        first_in_str = record.first_in.isoformat() if record.first_in else None
        last_out_str = record.last_out.isoformat() if record.last_out else None

        # Convert timedelta → PostgreSQL interval string
        work_hrs_str: Optional[str] = None
        if record.work_hours is not None:
            total_secs = int(record.work_hours.total_seconds())
            h, remainder = divmod(total_secs, 3600)
            m, s = divmod(remainder, 60)
            work_hrs_str = f"{h} hours {m} minutes {s} seconds"

        raw_json = json.dumps(record.raw_payload, default=str) if record.raw_payload else None

        is_late = record.status == AttendanceStatus.LATE or (
            record.first_in is not None
            and (
                record.first_in.hour > 9
                or (record.first_in.hour == 9 and record.first_in.minute > 0)
            )
        )

        # ── Perform upsert ─────────────────────────────────
        await db.execute(
            text("""
                INSERT INTO attendance_logs
                    (employee_id, log_date, first_in, last_out,
                     gross_work_hrs, status, is_late, data_source, raw_payload)
                VALUES
                    (:eid, :ld,
                     :fi ::timestamptz,
                     :lo ::timestamptz,
                     :wh ::interval,
                     :st, :is_late, :src,
                     :raw ::jsonb)
                ON CONFLICT (employee_id, log_date)
                DO UPDATE SET
                    first_in       = EXCLUDED.first_in,
                    last_out       = EXCLUDED.last_out,
                    gross_work_hrs = EXCLUDED.gross_work_hrs,
                    status         = EXCLUDED.status,
                    is_late        = EXCLUDED.is_late,
                    data_source    = EXCLUDED.data_source,
                    raw_payload    = EXCLUDED.raw_payload,
                    updated_at     = NOW()
                WHERE attendance_logs.data_source != 'MANUAL_CSV'
            """),
            {
                "eid": employee_id,
                "ld": record.log_date,
                "fi": first_in_str,
                "lo": last_out_str,
                "wh": work_hrs_str,
                "st": record.status.value,
                "is_late": is_late,
                "src": source,
                "raw": raw_json,
            },
        )

        if existing_row:
            return "updated"
        return "inserted"

    # ── Batch Sync ─────────────────────────────────────────

    async def sync_to_database(
        self,
        db: AsyncSession,
        raw_records: List[Dict[str, Any]],
        source: str = "API",
    ) -> CosecSyncResult:
        """
        End-to-end pipeline: validate raw API records and upsert them into
        the database in a single transaction.

        Args:
            db: Active async SQLAlchemy session.
            raw_records: Raw dicts from :meth:`fetch_daily_attendance`.
            source: Data source tag for provenance tracking.

        Returns:
            ``CosecSyncResult`` with counts and any error messages.
        """
        result = CosecSyncResult(total_fetched=len(raw_records))
        validated = self.validate_records(raw_records)

        for record in validated:
            try:
                outcome = await self.upsert_daily_record(
                    db, record, source=source, skip_manual=True
                )
                if outcome == "inserted":
                    result.inserted += 1
                elif outcome == "updated":
                    result.updated += 1
                else:
                    result.skipped += 1
            except Exception as exc:
                result.errors += 1
                msg = f"Upsert failed for {record.employee_code}/{record.log_date}: {exc}"
                result.error_messages.append(msg)
                logger.error(msg)

        # Commit the full batch
        try:
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.error("Transaction commit failed during COSEC sync: %s", exc)
            result.errors += 1
            result.error_messages.append(f"Commit failed: {exc}")

        logger.info(
            "COSEC sync complete — fetched=%d inserted=%d updated=%d skipped=%d errors=%d",
            result.total_fetched,
            result.inserted,
            result.updated,
            result.skipped,
            result.errors,
        )
        return result

    # ── Hybrid Cache: Live / Today ─────────────────────────

    async def get_today_attendance(
        self,
        employee_code: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch today's attendance for a specific employee, using a Redis
        cache with configurable TTL to reduce API load.

        Args:
            employee_code: The employee's COSEC user-id.

        Returns:
            Parsed record dict, or ``None`` if not available.
        """
        today = date.today()
        cache_key = f"attendance:today:{employee_code}:{today.isoformat()}"

        try:
            redis = await self._get_redis()
            cached = await redis.get(cache_key)
            if cached:
                logger.debug("Cache hit for %s", cache_key)
                return json.loads(cached)
        except Exception as exc:
            logger.warning("Redis unavailable for cache read: %s", exc)

        # Cache miss — call COSEC API
        today_fmt = today.strftime("%d/%m/%Y")
        raw_records = await self.fetch_daily_attendance(
            start_date=today_fmt,
            end_date=today_fmt,
            employee_id=employee_code,
        )

        if not raw_records:
            return None

        result = raw_records[0]

        # Write back to cache
        try:
            redis = await self._get_redis()
            await redis.setex(
                cache_key,
                timedelta(minutes=settings.LIVE_CACHE_TTL_MINUTES),
                json.dumps(result, default=str),
            )
        except Exception as exc:
            logger.warning("Redis unavailable for cache write: %s", exc)

        return result

    # ── Convenience: Fetch + Validate ──────────────────────

    async def fetch_and_validate(
        self,
        start_date: str,
        end_date: str,
        employee_id: Optional[str] = None,
    ) -> List[CosecDailyAttendanceRecord]:
        """
        Convenience method: fetch daily attendance from the API and return
        validated Pydantic records.

        Args:
            start_date: Start date in ``DD/MM/YYYY`` or ``YYYY-MM-DD``.
            end_date:   End date in the same format.
            employee_id: Optional employee filter.

        Returns:
            List of validated ``CosecDailyAttendanceRecord`` instances.
            Returns empty list on API failure.
        """
        raw = await self.fetch_daily_attendance(start_date, end_date, employee_id)
        if not raw:
            return []
        return self.validate_records(raw)

    # ── Legacy compatibility: date_range format ────────────

    async def fetch_daily_attendance_legacy(
        self,
        date_range: str,
        user_range: str = "all",
    ) -> List[Dict[str, Any]]:
        """
        Legacy interface matching the old ``DDMMYYYY-DDMMYYYY`` format.
        Converts to the new POST-based interface internally.

        Args:
            date_range: ``DDMMYYYY-DDMMYYYY`` range string.
            user_range: ``'all'`` or a specific user-id.

        Returns:
            Raw record dicts from the API.
        """
        parts = date_range.split("-")
        if len(parts) != 2 or len(parts[0]) != 8:
            logger.error("Invalid legacy date_range format: %s", date_range)
            return []

        start_raw, end_raw = parts
        start_fmt = f"{start_raw[:2]}/{start_raw[2:4]}/{start_raw[4:]}"
        end_fmt = f"{end_raw[:2]}/{end_raw[2:4]}/{end_raw[4:]}"

        emp_id = None if user_range == "all" else user_range
        return await self.fetch_daily_attendance(start_fmt, end_fmt, emp_id)


# ── Module-level singleton ─────────────────────────────────
cosec_service = MatrixCosecService()
