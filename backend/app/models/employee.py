"""
Employee ORM model — adjacency-list hierarchy via self-referencing manager_id.
"""
from sqlalchemy import (
    Column, Integer, String, Boolean, ForeignKey, DateTime
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    employee_code = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="EMPLOYEE")
    manager_id = Column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    department = Column(String(100))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # ── Authentication fields ────────────────────
    password_hash = Column(String(255), nullable=True)
    last_login = Column(DateTime(timezone=True), nullable=True)
    password_reset_required = Column(Boolean, default=True)
    failed_login_attempts = Column(Integer, default=0)
    account_locked_until = Column(DateTime(timezone=True), nullable=True)

    # ── Relationships ───────────────────────────
    # Navigate upward: employee.manager
    # NOTE: lazy="noload" prevents N+1 cascade — the old "selectin"
    # eagerly loaded the entire manager chain + all attendance_logs
    # on every Employee query, causing 2-3 min dashboard loads.
    manager = relationship(
        "Employee",
        remote_side=[id],
        backref="direct_reports",
        lazy="noload",
    )

    # Navigate downward: employee.attendance_logs
    attendance_logs = relationship(
        "AttendanceLog",
        back_populates="employee",
        lazy="noload",
    )

    def __repr__(self):
        return f"<Employee {self.employee_code} – {self.full_name}>"
