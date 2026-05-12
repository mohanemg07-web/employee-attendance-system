"""
Pydantic schemas for attendance data.
"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime


class AttendanceLogRead(BaseModel):
    id: int
    employee_id: int
    employee_name: Optional[str] = None
    employee_code: Optional[str] = None
    log_date: date
    first_in: Optional[datetime] = None
    last_out: Optional[datetime] = None
    gross_work_hrs: Optional[str] = None  # Interval serialised as string
    net_work_hrs: Optional[str] = None
    status: str = "PRESENT"
    data_source: str = "API"

    class Config:
        from_attributes = True


class AttendanceMonthlyRead(BaseModel):
    id: int
    employee_id: int
    employee_name: Optional[str] = None
    month: int
    year: int
    total_present: int = 0
    total_absent: int = 0
    total_late: int = 0
    total_half_day: int = 0
    total_leave: int = 0
    avg_work_hrs: Optional[str] = None
    data_source: str = "API"

    class Config:
        from_attributes = True


class TeamDailySummary(BaseModel):
    """Aggregated daily metrics for a manager's team."""
    date: date
    total_employees: int
    total_present: int
    total_absent: int
    total_late: int
    total_on_leave: int
    attendance_rate: float  # percentage


class CSVUploadResponse(BaseModel):
    filename: str
    total_rows: int
    inserted: int
    updated: int
    skipped: int
    errors: List[str] = []
