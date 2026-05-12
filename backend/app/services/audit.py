"""
Audit Logging service.
"""
import logging
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog

logger = logging.getLogger(__name__)

async def log_audit_event(
    db: AsyncSession,
    action: str,
    user_id: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Insert a structured event into the audit_logs table.

    Uses flush() instead of commit() so it participates in the caller's
    transaction. The caller is responsible for committing.
    Fails safely so it never breaks primary application flow.
    """
    try:
        audit = AuditLog(
            user_id=user_id,
            action=action,
            metadata_payload=metadata or {}
        )
        db.add(audit)
        await db.flush()
    except Exception as e:
        logger.warning("Audit log skipped for action '%s': %s", action, e)
        # Expunge the failed audit object so it doesn't pollute the session
        # DO NOT rollback — that would destroy the caller's pending data
        try:
            db.expunge(audit)
        except Exception:
            pass
