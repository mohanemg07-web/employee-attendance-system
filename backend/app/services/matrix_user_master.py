"""
Matrix COSEC User Master API client — async service.

Implements the ``Accessing User Data`` endpoint as documented in the
Matrix COSEC Web API User Guide (pp. 47–56):

* **Method:** ``GET`` with semicolon-separated query parameters.
* **URL pattern:** ``http://<server>/api.svc/v2/user?action=get;...``
* **Auth:** HTTP Basic (username/password from environment variables).
* **Response:** Pipe-delimited text with a header row and ``<EOT>`` terminator.

Environment variables consumed (via ``app.config.Settings``):
    MATRIX_COSEC_BASE_URL, MATRIX_COSEC_USERNAME, MATRIX_COSEC_PASSWORD
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import httpx
from pydantic import ValidationError

from app.config import get_settings
from app.schemas.user_sync import (
    UserMasterSyncSchema,
    remap_user_record,
)

logger = logging.getLogger(__name__)

# ── Fields we request from the COSEC API ───────────────────
# These are the tag names we need for the employees table + hierarchy.
# Requesting specific fields keeps response size manageable.
DEFAULT_USER_FIELDS = ",".join([
    "id",
    "reference-code",
    "name",
    "short-name",
    "full-name",
    "active",
    "personal-email",
    "official-email",
    "personal-phone",
    "personal-cell",
    "official-phone",
    "official-cell",
    "department",
    "designation",
    "department-name",
    "designation-name",
    "organization",
    "organization-name",
    "branch",
    "branch-name",
    "section",
    "section-name",
    "category",
    "category-name",
    "grade",
    "grade-name",
    "department_code",
    "designation_code",
    "organization_code",
    "branch_code",
    "section_code",
    "category_code",
    "grade_code",
    "reporting-incharge",
    "rg_id",
    "rg_name",
    "rg_incharge_1",
    "rg_incharge_2",
    "joining-date",
    "leaving-date",
    "date-of-birth",
    "gender",
    "marital-status",
    "blood-group",
    "nationality",
    "employment-profile",
    "employment-type",
    "leave_group",
])

# ── Retry configuration ───────────────────────────────────
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0  # seconds — exponential: 2, 4, 8


class MatrixUserMasterService:
    """
    Asynchronous service for fetching and parsing employee profile
    data from the Matrix COSEC User Master API.

    Usage::

        service = MatrixUserMasterService()
        raw = await service.fetch_all_users()
        validated = service.validate_records(raw)
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url: str = settings.MATRIX_COSEC_BASE_URL.rstrip("/")
        self.username: str = settings.MATRIX_COSEC_USERNAME
        self.password: str = settings.MATRIX_COSEC_PASSWORD

    def __repr__(self) -> str:
        return f"<MatrixUserMasterService url={self.base_url!r}>"

    # ── Public Fetch Methods ───────────────────────────────

    async def fetch_all_users(
        self,
        active_only: bool = True,
        field_names: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch all users the authenticated account has access to.

        Args:
            active_only: When ``True``, only returns active users
                (``active=1``).  The API does not have a native
                active-only filter in the ``get`` action, so we fetch
                all and filter afterwards.
            field_names: Comma-separated tag names.  Defaults to
                :data:`DEFAULT_USER_FIELDS`.

        Returns:
            List of raw record dicts from the pipe-delimited response.
        """
        fields = field_names or DEFAULT_USER_FIELDS

        params = [
            "action=get",
            "range=all",
            f"field-name={fields}",
        ]
        query_string = ";".join(params)
        url = f"{self.base_url}/api.svc/v2/user?{query_string}"

        records = await self._call_api(url)

        if active_only:
            # Filter for active_status == "1"
            records = [
                r for r in records
                if str(r.get("active", "1")).strip() == "1"
            ]
            logger.info(
                "Filtered to %d active users.", len(records)
            )

        return records

    async def fetch_users_by_org(
        self,
        org_id: int,
        field_names: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch all users belonging to a specific organization.

        Args:
            org_id: Organization ID (1–999999).
            field_names: Comma-separated tag names.

        Returns:
            List of raw record dicts.
        """
        fields = field_names or DEFAULT_USER_FIELDS

        params = [
            "action=get",
            "range=organization",
            f"id={org_id}",
            f"field-name={fields}",
        ]
        query_string = ";".join(params)
        url = f"{self.base_url}/api.svc/v2/user?{query_string}"

        return await self._call_api(url)

    async def fetch_user_by_id(
        self,
        user_id: str,
        field_names: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch a single user by their COSEC user ID (slot).

        Args:
            user_id: The COSEC user-id / slot number.
            field_names: Comma-separated tag names.

        Returns:
            List with 0 or 1 record dicts.
        """
        fields = field_names or DEFAULT_USER_FIELDS

        params = [
            "action=get",
            f"id={user_id}",
            f"field-name={fields}",
        ]
        query_string = ";".join(params)
        url = f"{self.base_url}/api.svc/v2/user?{query_string}"

        return await self._call_api(url)

    async def fetch_users_by_department(
        self,
        dept_id: int,
        field_names: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch all users belonging to a specific department.

        Args:
            dept_id: Department ID (1–999999).
            field_names: Comma-separated tag names.

        Returns:
            List of raw record dicts.
        """
        fields = field_names or DEFAULT_USER_FIELDS

        params = [
            "action=get",
            "range=department",
            f"id={dept_id}",
            f"field-name={fields}",
        ]
        query_string = ";".join(params)
        url = f"{self.base_url}/api.svc/v2/user?{query_string}"

        return await self._call_api(url)

    # ── Internal HTTP helper with retry ────────────────────

    async def _call_api(self, url: str) -> List[Dict[str, Any]]:
        """
        Execute an authenticated GET request against the COSEC User API
        and parse the pipe-delimited response.

        Implements exponential backoff retry for transient failures
        (timeouts, 5xx errors, connection errors).

        On permanent failure returns an empty list.
        """
        if len(url) > 2000:
            logger.warning(
                "COSEC User API URL is %d chars long — may hit "
                "server limits. Consider reducing requested fields.",
                len(url),
            )

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
                        "COSEC User API responded in %.2fs (attempt %d)",
                        elapsed,
                        attempt,
                    )
                    return self._parse_pipe_response(response.text)

            except httpx.TimeoutException as exc:
                last_exc = exc
                logger.warning(
                    "COSEC User API timeout (attempt %d/%d): GET %s",
                    attempt,
                    MAX_RETRIES,
                    url[:200],
                )

            except httpx.HTTPStatusError as exc:
                last_exc = exc
                # Only retry on 5xx (server-side); 4xx is permanent
                if exc.response.status_code < 500:
                    logger.error(
                        "COSEC User API HTTP %d (permanent): GET %s — %s",
                        exc.response.status_code,
                        url[:200],
                        exc.response.text[:500],
                    )
                    return []
                logger.warning(
                    "COSEC User API HTTP %d (attempt %d/%d): GET %s",
                    exc.response.status_code,
                    attempt,
                    MAX_RETRIES,
                    url[:200],
                )

            except httpx.RequestError as exc:
                last_exc = exc
                logger.warning(
                    "COSEC User API connection error (attempt %d/%d): %s",
                    attempt,
                    MAX_RETRIES,
                    exc,
                )

            except Exception as exc:
                logger.exception(
                    "Unexpected error calling COSEC User API: GET %s",
                    url[:200],
                )
                return []

            # Exponential backoff before retry
            if attempt < MAX_RETRIES:
                import asyncio
                wait = RETRY_BACKOFF_BASE ** attempt
                logger.info(
                    "Retrying COSEC User API in %.1fs...", wait
                )
                await asyncio.sleep(wait)

        # All retries exhausted
        logger.error(
            "COSEC User API failed after %d attempts: %s",
            MAX_RETRIES,
            last_exc,
        )
        return []

    # ── Response Parsing ───────────────────────────────────

    @staticmethod
    def _parse_pipe_response(body: str) -> List[Dict[str, Any]]:
        """
        Parse the COSEC pipe-delimited text response.

        **Format (from PDF p. 55-56):**

        .. code-block:: text

            id|name|reference-code|active|gender|marital-status|blood-group|nationality
            836|RAJUBHAI VANKAR|836|1|male|married|b+|Indian
            837|SHIRIN Y PATEL|837|1|female|unmarried|a-|Indian
            ...
            <EOT>

        Returns:
            List of dicts keyed by the header tag names.
        """
        records: List[Dict[str, Any]] = []
        lines = body.strip().splitlines()

        if not lines:
            logger.warning("COSEC User API returned an empty response.")
            return records

        # First line is the header
        header_line = lines[0].strip()
        headers = [h.strip().replace("\r", "") for h in header_line.split("|")]

        if len(headers) < 2:
            logger.error(
                "COSEC User API response header is malformed: %s",
                header_line[:200],
            )
            return records

        # Data rows
        for line_num, line in enumerate(lines[1:], start=2):
            stripped = line.strip()
            if not stripped or stripped.upper() == "<EOT>":
                continue

            values = [v.replace("\r", "") for v in stripped.split("|")]

            # The COSEC User API can return many fields; some rows
            # may have trailing pipe separators.  Pad if short.
            if len(values) < len(headers):
                values.extend([""] * (len(headers) - len(values)))

            # If row has MORE fields than headers (trailing pipe)
            # truncate to header length.
            values = values[: len(headers)]

            record = dict(zip(headers, values))
            records.append(record)

        logger.info(
            "Parsed %d user records from COSEC pipe-delimited response.",
            len(records),
        )
        return records

    # ── Record Validation ──────────────────────────────────

    def validate_records(
        self,
        raw_records: List[Dict[str, Any]],
    ) -> List[UserMasterSyncSchema]:
        """
        Validate and normalise a batch of raw record dicts through the
        ``UserMasterSyncSchema`` Pydantic schema.

        Invalid records are logged and skipped (fail-safe).

        Args:
            raw_records: Dicts from :meth:`_parse_pipe_response`.

        Returns:
            List of validated ``UserMasterSyncSchema`` instances.
        """
        validated: List[UserMasterSyncSchema] = []
        for idx, raw in enumerate(raw_records):
            try:
                mapped = remap_user_record(raw)
                record = UserMasterSyncSchema(**mapped)
                validated.append(record)
            except ValidationError as exc:
                logger.warning(
                    "Skipping invalid COSEC user record #%d: %s — raw=%s",
                    idx,
                    exc.errors(),
                    {k: v for k, v in raw.items()
                     if k in ("id", "name", "active")},
                )
        logger.info(
            "Validated %d / %d user records.",
            len(validated),
            len(raw_records),
        )
        return validated


# ── Module-level singleton ─────────────────────────────────
user_master_service = MatrixUserMasterService()
