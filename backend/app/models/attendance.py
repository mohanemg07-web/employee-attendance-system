"""
Attendance ORM models — daily logs and monthly summaries.
"""
from sqlalchemy import (
    Column, Integer, String, Date, Interval, ForeignKey, DateTime, Boolean, UniqueConstraint, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base, _is_sqlite

# Use JSONB on PostgreSQL (better indexing), fall back to JSON on SQLite
if _is_sqlite:
    from sqlalchemy import JSON as PayloadType
else:
    from sqlalchemy.dialects.postgresql import JSONB as PayloadType


class AttendanceLog(Base):
    __tablename__ = "attendance_logs"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    log_date = Column(Date, nullable=False)
    first_in = Column(DateTime(timezone=True), nullable=True)
    last_out = Column(DateTime(timezone=True), nullable=True)
    gross_work_hrs = Column(Interval, nullable=True)
    net_work_hrs = Column(Interval, nullable=True)
    status = Column(String(30), default="PRESENT")
    is_late = Column(Boolean, default=False)
    data_source = Column(String(20), nullable=False, default="API")
    raw_payload = Column(PayloadType, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("employee_id", "log_date", name="uq_employee_log_date"),
    )

    employee = relationship("Employee", back_populates="attendance_logs")

    def __repr__(self):
        return f"<AttendanceLog emp={self.employee_id} date={self.log_date} src={self.data_source}>"


class AttendanceMonthly(Base):
    __tablename__ = "attendance_monthly"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    total_present = Column(Integer, default=0)
    total_absent = Column(Integer, default=0)
    total_late = Column(Integer, default=0)
    total_half_day = Column(Integer, default=0)
    total_leave = Column(Integer, default=0)
    avg_work_hrs = Column(Interval, nullable=True)
    data_source = Column(String(20), nullable=False, default="API")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("employee_id", "month", "year", name="uq_employee_month_year"),
    )

    employee = relationship("Employee")

    def __repr__(self):
        return f"<AttendanceMonthly emp={self.employee_id} {self.month}/{self.year}>"
