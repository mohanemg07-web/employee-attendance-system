"""
Unified Matrix COSEC sync service facade.

Re-exports the three dedicated COSEC API services for convenience.
Each service handles one endpoint of the Matrix COSEC Web API:

* **User Master** — ``/api.svc/v2/user`` — employee profiles & hierarchy
* **Daily Attendance** — ``/api.svc/v2/attendance-daily`` — daily punch logs
* **Monthly Attendance** — ``/api.svc/v2/attendance-monthly`` — monthly summaries

Usage::

    from app.services.matrix_sync import (
        user_master_service,
        daily_attendance_service,
        monthly_service,
    )
"""
from app.services.matrix_user_master import (
    MatrixUserMasterService,
    user_master_service,
)
from app.services.matrix_daily import (
    MatrixDailyAttendanceService,
    daily_attendance_service,
)
from app.services.matrix_monthly import (
    monthly_service,
)

__all__ = [
    "MatrixUserMasterService",
    "user_master_service",
    "MatrixDailyAttendanceService",
    "daily_attendance_service",
    "monthly_service",
]
