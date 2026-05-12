"""
SyncLog ORM model — tracks biometric API sync operations.

Records every sync run (user/daily/monthly) with timing, record counts,
and error details for admin monitoring and debugging.
"""
from sqlalchemy import (
    Column, Integer, String, DateTime, JSON, Text
)
from sqlalchemy.sql import func

from app.database import Base


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id = Column(Integer, primary_key=True, index=True)

    # Type: USER, DAILY, MONTHLY
    sync_type = Column(String(20), nullable=False, index=True)

    # Status: RUNNING, SUCCESS, FAILED
    status = Column(String(20), nullable=False, default="RUNNING")

    # Who triggered: SCHEDULER, MANUAL
    triggered_by = Column(String(20), nullable=False, default="SCHEDULER")

    # Timing
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Record counts
    records_fetched = Column(Integer, default=0)
    records_inserted = Column(Integer, default=0)
    records_updated = Column(Integer, default=0)
    records_skipped = Column(Integer, default=0)
    records_errors = Column(Integer, default=0)

    # Duration in seconds
    duration_seconds = Column(Integer, nullable=True)

    # Error details (JSON array of error messages)
    error_log = Column(JSON, nullable=True)

    # Optional metadata (date range synced, etc.)
    metadata_payload = Column(JSON, nullable=True)

    def __repr__(self):
        return (
            f"<SyncLog id={self.id} type={self.sync_type} "
            f"status={self.status} fetched={self.records_fetched}>"
        )
