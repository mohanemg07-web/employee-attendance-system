"""
Unified Biometric API Client — single entry point for Matrix COSEC integration.

Wraps all COSEC API services and the sync orchestrator into a clean,
high-level interface. Environment-variable driven via ``app.config.Settings``.

Usage::

    from app.services.biometric_client import biometric_client

    result = await biometric_client.sync_employees()
    result = await biometric_client.sync_today()
    result = await biometric_client.sync_daily_attendance(start, end)
    result = await biometric_client.sync_monthly_attendance(month=5, year=2026)
    results = await biometric_client.run_full_sync()
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from app.config import get_settings

logger = logging.getLogger(__name__)


class BiometricClient:
    """Unified facade for Matrix COSEC biometric API integration."""

    def __init__(self) -> None:
        s = get_settings()
        self.base_url = s.MATRIX_COSEC_BASE_URL
        self.username = s.MATRIX_COSEC_USERNAME
        self.sync_interval = s.SYNC_INTERVAL_MINUTES
        self.sync_enabled = s.BIOMETRIC_SYNC_ENABLED

    def __repr__(self) -> str:
        return f"<BiometricClient url={self.base_url!r} enabled={self.sync_enabled}>"

    @property
    def is_configured(self) -> bool:
        """True when the COSEC base URL is set."""
        return bool(self.base_url and self.base_url.strip())

    # ── User / Employee Sync ──────────────────────────────

    async def sync_employees(self, triggered_by: str = "MANUAL") -> Dict[str, Any]:
        """Sync all active users from COSEC → employees table."""
        from app.services.sync_orchestrator import sync_orchestrator
        return await sync_orchestrator.sync_users(triggered_by=triggered_by)

    # ── Daily Attendance Sync ─────────────────────────────

    async def sync_daily_attendance(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        triggered_by: str = "MANUAL",
    ) -> Dict[str, Any]:
        """Sync daily attendance for a date range → attendance_logs."""
        from app.services.sync_orchestrator import sync_orchestrator
        return await sync_orchestrator.sync_daily(
            start_date=start_date,
            end_date=end_date,
            triggered_by=triggered_by,
        )

    async def sync_today(self, triggered_by: str = "MANUAL") -> Dict[str, Any]:
        """Convenience: sync today's attendance."""
        today = date.today()
        return await self.sync_daily_attendance(today, today, triggered_by)

    async def sync_yesterday(self, triggered_by: str = "MANUAL") -> Dict[str, Any]:
        """Convenience: sync yesterday's attendance."""
        y = date.today() - timedelta(days=1)
        return await self.sync_daily_attendance(y, y, triggered_by)

    # ── Monthly Attendance Sync ───────────────────────────

    async def sync_monthly_attendance(
        self,
        month: Optional[int] = None,
        year: Optional[int] = None,
        triggered_by: str = "MANUAL",
    ) -> Dict[str, Any]:
        """Sync monthly summaries from COSEC → attendance_monthly."""
        from app.services.sync_orchestrator import sync_orchestrator
        return await sync_orchestrator.sync_monthly(month=month, year=year, triggered_by=triggered_by)

    # ── Full Sync ──────────────────────────────────────────

    async def run_full_sync(self, triggered_by: str = "MANUAL") -> Dict[str, Any]:
        """Run complete sync cycle: users → daily → monthly."""
        results: Dict[str, Any] = {"triggered_by": triggered_by}

        logger.info("[BiometricClient] Full sync: Phase 1 — Users")
        results["users"] = await self.sync_employees(triggered_by)

        logger.info("[BiometricClient] Full sync: Phase 2 — Daily")
        yesterday = date.today() - timedelta(days=1)
        results["daily"] = await self.sync_daily_attendance(yesterday, date.today(), triggered_by)

        logger.info("[BiometricClient] Full sync: Phase 3 — Monthly")
        results["monthly"] = await self.sync_monthly_attendance(triggered_by=triggered_by)

        all_ok = all(
            results.get(p, {}).get("status") == "SUCCESS"
            for p in ("users", "daily", "monthly")
        )
        results["status"] = "SUCCESS" if all_ok else "PARTIAL_FAILURE"
        logger.info("[BiometricClient] Full sync: %s", results["status"])
        return results

    # ── Sync Status ────────────────────────────────────────

    async def get_sync_status(self, limit: int = 10, sync_type: Optional[str] = None) -> List[Dict]:
        """Retrieve recent sync logs from the database."""
        from sqlalchemy import text
        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            q = "SELECT * FROM sync_logs"
            params: Dict[str, Any] = {"limit": limit}
            if sync_type:
                q += " WHERE sync_type = :sync_type"
                params["sync_type"] = sync_type.upper()
            q += " ORDER BY started_at DESC LIMIT :limit"
            result = await db.execute(text(q), params)
            return [dict(zip(result.keys(), row)) for row in result.fetchall()]

    async def get_last_sync(self, sync_type: str = "DAILY") -> Optional[Dict]:
        """Get the most recent sync log for a given type."""
        logs = await self.get_sync_status(limit=1, sync_type=sync_type)
        return logs[0] if logs else None

    # ── Low-level Service Access ──────────────────────────

    @staticmethod
    def get_user_master_service():
        """Return the MatrixUserMasterService singleton."""
        from app.services.matrix_user_master import user_master_service
        return user_master_service

    @staticmethod
    def get_daily_service():
        """Return the MatrixDailyAttendanceService singleton."""
        from app.services.matrix_daily import daily_attendance_service
        return daily_attendance_service

    @staticmethod
    def get_monthly_service():
        """Return the MatrixMonthlyService singleton."""
        from app.services.matrix_monthly import monthly_service
        return monthly_service


# ── Module-level singleton ─────────────────────────────────
biometric_client = BiometricClient()
