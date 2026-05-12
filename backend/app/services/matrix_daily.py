"""
Matrix COSEC Daily Attendance API client — async service.

Implements the ``Getting Daily Attendance Data`` endpoint as documented
in the Matrix COSEC Web API User Guide (pp. 96–105):

* **Method:** ``GET`` with semicolon-separated query parameters.
* **URL pattern:**
  ``http://<server>/api.svc/v2/attendance-daily?action=get;<args>``
* **Auth:** HTTP Basic (username/password from environment variables).
* **Response:** Pipe-delimited text with a header row and ``<EOT>`` terminator.

**Parameters from PDF (p. 96–97):**
    field-name     comma-separated tag names
    date-range     ddmmyyyy-ddmmyyyy
    range          all | user | organization | branch | department | ...
    Id             1-999 (user or org/dept/branch IDs)
    shift-end-elapsed  HH:MM-HH:MM
    return-field-name  0 | 1 | 2
    Active         0 | 1 | 2

Environment variables consumed (via ``app.config.Settings``):
    MATRIX_COSEC_BASE_URL, MATRIX_COSEC_USERNAME, MATRIX_COSEC_PASSWORD
"""
from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any, Dict, List, Optional

import httpx
from pydantic import ValidationError

from app.config import get_settings
from app.schemas.daily_sync import (
    DailyAttendanceSyncSchema,
    remap_daily_record,
)

logger = logging.getLogger(__name__)


# ── Fields we request from the COSEC Daily Attendance API ──
# These are the tag names from the PDF Response Fields table
# that we need for the attendance_logs table.
DEFAULT_DAILY_FIELDS = ",".join([
    "USERID",
    "USERNAME",
    "PROCESSDATE",
    "PUNCH1",
    "PUNCH1_DATE",
    "PUNCH1_TIME",
    "PUNCH2",
    "PUNCH2_DATE",
    "PUNCH2_TIME",
    "OUTPUNCH",
    "OUTPUNCH_DATE",
    "OUTPUNCH_TIME",
    "WORKTIME",
    "WORKTIME_HHMM",
    "NETWORKHRS",
    "OVERTIME",
    "LATEIN",
    "LATEIN_HHMM",
    "EARLYOUT",
    "EARLYOUT_HHMM",
    "FIRSTHALF",
    "SECONDHALF",
    "DAYSTATUS",
    "WEEKOFFANDHOLIDAY",
    "WORKINGSHIFT",
    "SHIFTSTART",
    "SHIFTEND",
    "SUMMARY",
])

# ── Retry configuration ───────────────────────────────────
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0  # seconds — exponential: 2, 4, 8


class MatrixDailyAttendanceService:
    """
    Asynchronous service for fetching and parsing daily attendance
    records from the Matrix COSEC API.

    Usage::

        service = MatrixDailyAttendanceService()
        raw = await service.fetch_daily_attendance(
            start_date=date(2026, 4, 28),
            end_date=date(2026, 4, 28),
        )
        validated = service.validate_records(raw)
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url: str = settings.MATRIX_COSEC_BASE_URL.rstrip("/")
        self.username: str = settings.MATRIX_COSEC_USERNAME
        self.password: str = settings.MATRIX_COSEC_PASSWORD

    def __repr__(self) -> str:
        return f"<MatrixDailyAttendanceService url={self.base_url!r}>"

    # ── Public Fetch Methods ───────────────────────────────

    async def fetch_daily_attendance(
        self,
        start_date: date,
        end_date: Optional[date] = None,
        field_names: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch daily attendance records for all users within a date range.

        Args:
            start_date: Start date (inclusive).
            end_date: End date (inclusive). Defaults to ``start_date``.
            field_names: Comma-separated tag names. Defaults to
                :data:`DEFAULT_DAILY_FIELDS`.

        Returns:
            List of raw record dicts from the pipe-delimited response.
        """
        end = end_date or start_date
        fields = field_names or DEFAULT_DAILY_FIELDS

        date_range = (
            f"{start_date.strftime('%d%m%Y')}-{end.strftime('%d%m%Y')}"
        )

        params = [
            "action=get",
            "range=all",
            f"date-range={date_range}",
            f"field-name={fields}",
        ]
        query_string = ";".join(params)
        url = f"{self.base_url}/api.svc/v2/attendance-daily?{query_string}"

        records = await self._call_api(url)

        logger.info(
            "Fetched %d daily attendance records for date-range %s.",
            len(records),
            date_range,
        )
        return records

    async def fetch_daily_by_user(
        self,
        user_id: str,
        start_date: date,
        end_date: Optional[date] = None,
        field_names: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch daily attendance for a specific user by their COSEC ID.

        Args:
            user_id: The COSEC user-id / slot number.
            start_date: Start date (inclusive).
            end_date: End date (inclusive). Defaults to ``start_date``.
            field_names: Comma-separated tag names.

        Returns:
            List of raw record dicts.
        """
        end = end_date or start_date
        fields = field_names or DEFAULT_DAILY_FIELDS

        date_range = (
            f"{start_date.strftime('%d%m%Y')}-{end.strftime('%d%m%Y')}"
        )

        params = [
            "action=get",
            "range=user",
            f"Id={user_id}",
            f"date-range={date_range}",
            f"field-name={fields}",
        ]
        query_string = ";".join(params)
        url = f"{self.base_url}/api.svc/v2/attendance-daily?{query_string}"

        return await self._call_api(url)

    async def fetch_daily_by_department(
        self,
        dept_id: int,
        start_date: date,
        end_date: Optional[date] = None,
        field_names: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch daily attendance for all users in a department.

        Args:
            dept_id: Department ID (1–999999).
            start_date: Start date (inclusive).
            end_date: End date (inclusive).
            field_names: Comma-separated tag names.

        Returns:
            List of raw record dicts.
        """
        end = end_date or start_date
        fields = field_names or DEFAULT_DAILY_FIELDS

        date_range = (
            f"{start_date.strftime('%d%m%Y')}-{end.strftime('%d%m%Y')}"
        )

        params = [
            "action=get",
            "range=department",
            f"Id={dept_id}",
            f"date-range={date_range}",
            f"field-name={fields}",
        ]
        query_string = ";".join(params)
        url = f"{self.base_url}/api.svc/v2/attendance-daily?{query_string}"

        return await self._call_api(url)

    # ── Internal HTTP helper with retry ────────────────────

    async def _call_api(self, url: str) -> List[Dict[str, Any]]:
        """
        Execute an authenticated GET request against the COSEC Daily
        Attendance API and parse the pipe-delimited response.

        Implements exponential backoff retry for transient failures
        (timeouts, 5xx errors, connection errors).

        On permanent failure returns an empty list.
        """
        if len(url) > 2000:
            logger.warning(
                "COSEC Daily API URL is %d chars long — may hit "
                "server limits. Consider reducing requested fields.",
                len(url),
            )

        last_exc: Optional[Exception] = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(
                        connect=10.0, read=90.0, write=10.0, pool=10.0
                    ),
                ) as client:
                    t0 = time.monotonic()
                    response = await client.get(
                        url,
                        auth=(self.username, self.password),
                    )
                    elapsed = time.monotonic() - t0
                    response.raise_for_status()

                    logger.debug(
                        "COSEC Daily API responded in %.2fs (attempt %d)",
                        elapsed,
                        attempt,
                    )
                    return self._parse_pipe_response(response.text)

            except httpx.TimeoutException as exc:
                last_exc = exc
                logger.warning(
                    "COSEC Daily API timeout (attempt %d/%d): GET %s",
                    attempt,
                    MAX_RETRIES,
                    url[:200],
                )

            except httpx.HTTPStatusError as exc:
                last_exc = exc
                # Only retry on 5xx (server-side); 4xx is permanent
                if exc.response.status_code < 500:
                    logger.error(
                        "COSEC Daily API HTTP %d (permanent): GET %s — %s",
                        exc.response.status_code,
                        url[:200],
                        exc.response.text[:500],
                    )
                    return []
                logger.warning(
                    "COSEC Daily API HTTP %d (attempt %d/%d): GET %s",
                    exc.response.status_code,
                    attempt,
                    MAX_RETRIES,
                    url[:200],
                )

            except httpx.RequestError as exc:
                last_exc = exc
                logger.warning(
                    "COSEC Daily API connection error (attempt %d/%d): %s",
                    attempt,
                    MAX_RETRIES,
                    exc,
                )

            except Exception as exc:
                logger.exception(
                    "Unexpected error calling COSEC Daily API: GET %s",
                    url[:200],
                )
                return []

            # Exponential backoff before retry
            if attempt < MAX_RETRIES:
                import asyncio
                wait = RETRY_BACKOFF_BASE ** attempt
                logger.info(
                    "Retrying COSEC Daily API in %.1fs...", wait
                )
                await asyncio.sleep(wait)

        # All retries exhausted
        logger.error(
            "COSEC Daily API failed after %d attempts: %s",
            MAX_RETRIES,
            last_exc,
        )
        return []

    # ── Response Parsing ───────────────────────────────────

    @staticmethod
    def _parse_pipe_response(body: str) -> List[Dict[str, Any]]:
        """
        Parse the COSEC pipe-delimited text response.

        **Format (from PDF p. 104-105):**

        .. code-block:: text

            UserID|USER NAME|ProcessDate|Punch1|Punch2|WorkingShift|LateIn|EARLY OUT|Overtime|WorkTime
            vegaworker|vegaworker|02/01/2018|01/01/2018 22:23:38||GS||||
            <EOT>

        Returns:
            List of dicts keyed by the header tag names.
        """
        records: List[Dict[str, Any]] = []
        lines = body.strip().splitlines()

        if not lines:
            logger.warning(
                "COSEC Daily API returned an empty response."
            )
            return records

        # First line is the header
        header_line = lines[0].strip()
        headers = [h.strip().replace("\r", "") for h in header_line.split("|")]

        if len(headers) < 2:
            logger.error(
                "COSEC Daily API response header is malformed: %s",
                header_line[:200],
            )
            return records

        # Data rows
        for line_num, line in enumerate(lines[1:], start=2):
            stripped = line.strip()
            if not stripped or stripped.upper() == "<EOT>":
                continue

            values = [v.replace("\r", "") for v in stripped.split("|")]

            # Pad short rows
            if len(values) < len(headers):
                values.extend([""] * (len(headers) - len(values)))

            # Truncate rows with trailing pipes
            values = values[: len(headers)]

            record = dict(zip(headers, values))
            records.append(record)

        logger.info(
            "Parsed %d daily attendance records from "
            "COSEC pipe-delimited response.",
            len(records),
        )
        return records

    # ── Record Validation ──────────────────────────────────

    def validate_records(
        self,
        raw_records: List[Dict[str, Any]],
    ) -> List[DailyAttendanceSyncSchema]:
        """
        Validate and normalise a batch of raw record dicts through the
        ``DailyAttendanceSyncSchema`` Pydantic schema.

        Invalid records are logged and skipped (fail-safe).

        Args:
            raw_records: Dicts from :meth:`_parse_pipe_response`.

        Returns:
            List of validated ``DailyAttendanceSyncSchema`` instances.
        """
        validated: List[DailyAttendanceSyncSchema] = []
        for idx, raw in enumerate(raw_records):
            try:
                mapped = remap_daily_record(raw)
                record = DailyAttendanceSyncSchema(**mapped)

                # Skip records with no parseable date
                if record.log_date is None:
                    logger.warning(
                        "Skipping COSEC daily record #%d: "
                        "no parseable date — raw=%s",
                        idx,
                        {k: v for k, v in raw.items()
                         if k in ("USERID", "UserID", "PROCESSDATE")},
                    )
                    continue

                validated.append(record)
            except ValidationError as exc:
                logger.warning(
                    "Skipping invalid COSEC daily record #%d: %s — raw=%s",
                    idx,
                    exc.errors(),
                    {k: v for k, v in raw.items()
                     if k in ("USERID", "UserID", "PROCESSDATE",
                              "ProcessDate")},
                )
        logger.info(
            "Validated %d / %d daily attendance records.",
            len(validated),
            len(raw_records),
        )
        return validated


# ── Module-level singleton ─────────────────────────────────
daily_attendance_service = MatrixDailyAttendanceService()
