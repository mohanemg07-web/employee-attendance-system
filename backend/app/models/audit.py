from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func, JSON
from sqlalchemy.orm import Mapped, mapped_column
from typing import Dict, Any

from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String, index=True, nullable=False)
    timestamp: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    metadata_payload: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=True)

    def __repr__(self):
        return f"<AuditLog id={self.id} action={self.action} user_id={self.user_id}>"
