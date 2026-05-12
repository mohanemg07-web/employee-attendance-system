"""
Matrix COSEC Monthly Attendance API client — async service.

Implements the ``Getting Monthly Attendance Data`` endpoint as documented
in the Matrix COSEC Web API User Guide (pp. 106–113):

* **Method:** ``GET`` with semicolon-separated query parameters.
* **URL pattern:** ``http://<server>/api.svc/v2/attendance-monthly?action=get;...``
* **Auth:** HTTP Basic (username/password from environment variables).
* **Response:** Pipe-delimited text with a header row and ``<EOT>`` terminator.

Environment variables consumed (via ``app.config.Settings``):
    MATRIX_COSEC_BASE_URL, MATRIX_COSEC_USERNAME, MATRIX_COSEC_PASSWORD
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from pydantic import ValidationError

from app.config import get_settings
from app.schemas.monthly_sync import (
    MonthlyAttendanceSyncSchema,
    remap_monthly_record,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Retry configuration ───────────────────────────────────
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0  # seconds — exponential: 2, 4, 8


class MatrixMonthlyService:
    """
    Asynchronous service for fetching and parsing monthly attendance
    data from the Matrix COSEC biometric API.

    Usage::

        service = MatrixMonthlyService()
        raw = await service.fetch_monthly_attendance(month=4, year=2026)
        validated = service.validate_records(raw)
    """

    def __init__(self) -> None:
        self.base_url: str = settings.MATRIX_COSEC_BASE_URL.rstrip("/")
        self.username: str = settings.MATRIX_COSEC_USERNAME
        self.password: str = settings.MATRIX_COSEC_PASSWORD

    def __repr__(self) -> str:
        return f"<MatrixMonthlyService url={self.base_url!r}>"

    # ── API Communication ──────────────────────────────────

    async def fetch_monthly_attendance(
        self,
        month: Optional[int] = None,
        year: Optional[int] = None,
        range_type: str = "all",
        range_id: Optional[int] = None,
        field_names: Optional[str] = None,
        active: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        Fetch monthly attendance data from the COSEC API.

        Args:
            month: 1–12.  Defaults to current month.
            year:  4-digit year.  Defaults to current year.
            range_type: One of ``'all'``, ``'organization'``, ``'branch'``,
                ``'department'``, ``'designation'``, ``'section'``,
                ``'category'``, ``'grade'``, ``'user'``.
            range_id: Mandatory when ``range_type`` is not ``'all'``.
                For ``'user'`` range, this is the numeric user slot.
            field_names: Comma-separated tag names to request specific
                fields (e.g. ``"USERID,USERNAME,PRDAYS"``).
                When ``None``, the API returns all configured fields.
            active: ``1`` = active only (default), ``0`` = inactive,
                ``2`` = all.

        Returns:
            List of raw record dicts parsed from the pipe-delimited
            response, or an empty list on any failure.
        """
        now = datetime.now()
        m = month or now.month
        y = year or now.year
        month_year = f"{m:02d}{y:04d}"

        # Build semicolon-separated query string per COSEC syntax
        params: List[str] = [
            "action=get",
            f"month-year={month_year}",
            f"range={range_type}",
            f"active={active}",
            "return-field-name=1",  # Use actual field (tag) names
        ]

        if range_type != "all" and range_id is not None:
            params.append(f"id={range_id}")

        if field_names:
            params.append(f"field-name={field_names}")

        query_string = ";".join(params)
        url = f"{self.base_url}/api.svc/v2/attendance-monthly?{query_string}"

        return await self._call_api(url)

    async def fetch_monthly_for_user(
        self,
        user_id: str,
        month: Optional[int] = None,
        year: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Convenience method: fetch monthly data for a single user.

        Args:
            user_id: The COSEC user-id / slot number.
            month: 1–12 (defaults to current).
            year: 4-digit year (defaults to current).

        Returns:
            List with 0 or 1 record dicts.
        """
        now = datetime.now()
        m = month or now.month
        y = year or now.year
        month_year = f"{m:02d}{y:04d}"

        params = [
            "action=get",
            f"month-year={month_year}",
            "range=user",
            f"id={user_id}",
            "return-field-name=1",
        ]
        query_string = ";".join(params)
        url = f"{self.base_url}/api.svc/v2/attendance-monthly?{query_string}"

        return await self._call_api(url)

    # ── Internal HTTP helper with retry ────────────────────

    async def _call_api(self, url: str) -> List[Dict[str, Any]]:
        """
        Execute an authenticated GET request against the COSEC Monthly API
        and parse the pipe-delimited response.

        Implements exponential backoff retry for transient failures
        (timeouts, 5xx errors, connection errors).

        On permanent failure returns an empty list.
        """
        last_exc: Optional[Exception] = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(
                        connect=10.0, read=60.0, write=10.0, pool=10.0
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
                        "COSEC Monthly API responded in %.2fs (attempt %d)",
                        elapsed,
                        attempt,
                    )
                    return self._parse_pipe_response(response.text)

            except httpx.TimeoutException as exc:
                last_exc = exc
                logger.warning(
                    "COSEC Monthly API timeout (attempt %d/%d): GET %s",
                    attempt,
                    MAX_RETRIES,
                    url[:200],
                )

            except httpx.HTTPStatusError as exc:
                last_exc = exc
                # Only retry on 5xx (server-side); 4xx is permanent
                if exc.response.status_code < 500:
                    logger.error(
                        "COSEC Monthly API HTTP %d (permanent): GET %s — %s",
                        exc.response.status_code,
                        url[:200],
                        exc.response.text[:500],
                    )
                    return []
                logger.warning(
                    "COSEC Monthly API HTTP %d (attempt %d/%d): GET %s",
                    exc.response.status_code,
                    attempt,
                    MAX_RETRIES,
                    url[:200],
                )

            except httpx.RequestError as exc:
                last_exc = exc
                logger.warning(
                    "COSEC Monthly API connection error (attempt %d/%d): %s",
                    attempt,
                    MAX_RETRIES,
                    exc,
                )

            except Exception as exc:
                logger.exception(
                    "Unexpected error calling COSEC Monthly API: GET %s",
                    url[:200],
                )
                return []

            # Exponential backoff before retry
            if attempt < MAX_RETRIES:
                import asyncio
                wait = RETRY_BACKOFF_BASE ** attempt
                logger.info(
                    "Retrying COSEC Monthly API in %.1fs...", wait
                )
                await asyncio.sleep(wait)

        # All retries exhausted
        logger.error(
            "COSEC Monthly API failed after %d attempts: %s",
            MAX_RETRIES,
            last_exc,
        )
        return []

    # ── Response Parsing ───────────────────────────────────

    @staticmethod
    def _parse_pipe_response(body: str) -> List[Dict[str, Any]]:
        """
        Parse the COSEC pipe-delimited text response.

        **Format (from PDF p. 113):**

        .. code-block:: text

            UserID|UserName|PYear|PMonth|PRDays|ABDays|WorkTime_HHMM|PLDays|TRDays
            007|ANAND RATHOD|2015|1|0.0|23.0|000:00|0.0|0.0
            1053|JINU SAM|2015|1|19.5|0.5|197:20|2.0|0.0
            ...
            <EOT>

        Returns:
            List of dicts keyed by the header tag names.
        """
        records: List[Dict[str, Any]] = []
        lines = body.strip().splitlines()

        if not lines:
            logger.warning("COSEC Monthly API returned an empty response.")
            return records

        # First line is the header
        header_line = lines[0].strip()
        headers = [h.strip() for h in header_line.split("|")]

        if len(headers) < 2:
            logger.error(
                "COSEC Monthly API response header is malformed: %s",
                header_line[:200],
            )
            return records

        # Data rows
        for line_num, line in enumerate(lines[1:], start=2):
            stripped = line.strip()
            if not stripped or stripped.upper() == "<EOT>":
                continue

            values = stripped.split("|")

            if len(values) != len(headers):
                logger.warning(
                    "COSEC Monthly: line %d has %d fields, expected %d — skipping: %s",
                    line_num,
                    len(values),
                    len(headers),
                    stripped[:200],
                )
                continue

            record = dict(zip(headers, values))
            records.append(record)

        logger.info(
            "Parsed %d monthly records from COSEC pipe-delimited response.",
            len(records),
        )
        return records

    # ── Record Validation ──────────────────────────────────

    def validate_records(
        self,
        raw_records: List[Dict[str, Any]],
    ) -> List[MonthlyAttendanceSyncSchema]:
        """
        Validate and normalise a batch of raw record dicts through the
        ``MonthlyAttendanceSyncSchema`` Pydantic schema.

        Invalid records are logged and skipped (fail-safe).

        Args:
            raw_records: Dicts from :meth:`_parse_pipe_response`.

        Returns:
            List of validated ``MonthlyAttendanceSyncSchema`` instances.
        """
        validated: List[MonthlyAttendanceSyncSchema] = []
        for idx, raw in enumerate(raw_records):
            try:
                mapped = remap_monthly_record(raw)
                record = MonthlyAttendanceSyncSchema(**mapped)
                validated.append(record)
            except ValidationError as exc:
                logger.warning(
                    "Skipping invalid COSEC monthly record #%d: %s — raw=%s",
                    idx,
                    exc.errors(),
                    raw,
                )
        logger.info(
            "Validated %d / %d monthly records.", len(validated), len(raw_records)
        )
        return validated


# ── Module-level singleton ─────────────────────────────────
monthly_service = MatrixMonthlyService()
