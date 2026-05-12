"""Quick import test to verify all backend modules load correctly."""
import sys
sys.path.insert(0, '.')

errors = []

# Test 1: Config
try:
    from app.config import get_settings
    settings = get_settings()
    print("[PASS] app.config")
except Exception as e:
    errors.append(f"[FAIL] app.config: {e}")
    print(f"[FAIL] app.config: {e}")

# Test 2: Database
try:
    from app.database import Base, engine, AsyncSessionLocal
    print("[PASS] app.database")
except Exception as e:
    errors.append(f"[FAIL] app.database: {e}")
    print(f"[FAIL] app.database: {e}")

# Test 3: Models
try:
    from app.models import Employee, AttendanceLog, AttendanceMonthly
    print("[PASS] app.models")
except Exception as e:
    errors.append(f"[FAIL] app.models: {e}")
    print(f"[FAIL] app.models: {e}")

# Test 4: Schemas
try:
    from app.schemas.auth import TokenResponse, UserProfile
    from app.schemas.employee import EmployeeRead, EmployeeNode
    from app.schemas.attendance import AttendanceLogRead, CSVUploadResponse
    print("[PASS] app.schemas")
except Exception as e:
    errors.append(f"[FAIL] app.schemas: {e}")
    print(f"[FAIL] app.schemas: {e}")

# Test 5: Security utils
try:
    from app.utils.security import create_access_token, decode_token
    token = create_access_token({"sub": "test@test.com", "employee_id": 1, "role": "EMPLOYEE"})
    payload = decode_token(token)
    assert payload["sub"] == "test@test.com"
    print("[PASS] app.utils.security (JWT create+decode)")
except Exception as e:
    errors.append(f"[FAIL] app.utils.security: {e}")
    print(f"[FAIL] app.utils.security: {e}")

# Test 6: Services
try:
    from app.services.hierarchy import get_subordinate_ids, get_hierarchy_tree
    print("[PASS] app.services.hierarchy")
except Exception as e:
    errors.append(f"[FAIL] app.services.hierarchy: {e}")
    print(f"[FAIL] app.services.hierarchy: {e}")

try:
    from app.services.matrix_cosec import cosec_service, MatrixCosecService
    print("[PASS] app.services.matrix_cosec")
except Exception as e:
    errors.append(f"[FAIL] app.services.matrix_cosec: {e}")
    print(f"[FAIL] app.services.matrix_cosec: {e}")

try:
    from app.services.csv_parser import parse_attendance_file, normalise_columns
    print("[PASS] app.services.csv_parser")
except Exception as e:
    errors.append(f"[FAIL] app.services.csv_parser: {e}")
    print(f"[FAIL] app.services.csv_parser: {e}")

# Test 7b: COSEC Integration Schemas
try:
    from app.schemas.cosec import CosecDailyAttendanceRecord, CosecSyncResult
    print("[PASS] app.schemas.cosec")
except Exception as e:
    errors.append(f"[FAIL] app.schemas.cosec: {e}")
    print(f"[FAIL] app.schemas.cosec: {e}")

try:
    from app.schemas.monthly_sync import MonthlyAttendanceSyncSchema, MonthlySyncResult
    print("[PASS] app.schemas.monthly_sync")
except Exception as e:
    errors.append(f"[FAIL] app.schemas.monthly_sync: {e}")
    print(f"[FAIL] app.schemas.monthly_sync: {e}")

try:
    from app.schemas.user_sync import UserMasterSyncSchema, UserSyncResult
    print("[PASS] app.schemas.user_sync")
except Exception as e:
    errors.append(f"[FAIL] app.schemas.user_sync: {e}")
    print(f"[FAIL] app.schemas.user_sync: {e}")

# Test 7c: COSEC Integration Services
try:
    from app.services.matrix_monthly import monthly_service
    print("[PASS] app.services.matrix_monthly")
except Exception as e:
    errors.append(f"[FAIL] app.services.matrix_monthly: {e}")
    print(f"[FAIL] app.services.matrix_monthly: {e}")

try:
    from app.services.matrix_user_master import user_master_service
    print("[PASS] app.services.matrix_user_master")
except Exception as e:
    errors.append(f"[FAIL] app.services.matrix_user_master: {e}")
    print(f"[FAIL] app.services.matrix_user_master: {e}")

# Test 7d: COSEC Integration CRUD
try:
    from app.crud.crud_monthly import sync_monthly_batch, upsert_monthly_record
    print("[PASS] app.crud.crud_monthly")
except Exception as e:
    errors.append(f"[FAIL] app.crud.crud_monthly: {e}")
    print(f"[FAIL] app.crud.crud_monthly: {e}")

try:
    from app.crud.crud_user import sync_users_full, upsert_employee_batch, link_manager_hierarchy
    print("[PASS] app.crud.crud_user")
except Exception as e:
    errors.append(f"[FAIL] app.crud.crud_user: {e}")
    print(f"[FAIL] app.crud.crud_user: {e}")

# Test 7e: Daily Attendance Integration
try:
    from app.schemas.daily_sync import DailyAttendanceSyncSchema, DailySyncResult
    print("[PASS] app.schemas.daily_sync")
except Exception as e:
    errors.append(f"[FAIL] app.schemas.daily_sync: {e}")
    print(f"[FAIL] app.schemas.daily_sync: {e}")

try:
    from app.services.matrix_daily import daily_attendance_service
    print("[PASS] app.services.matrix_daily")
except Exception as e:
    errors.append(f"[FAIL] app.services.matrix_daily: {e}")
    print(f"[FAIL] app.services.matrix_daily: {e}")

try:
    from app.crud.crud_daily import upsert_daily_batch, upsert_daily_record
    print("[PASS] app.crud.crud_daily")
except Exception as e:
    errors.append(f"[FAIL] app.crud.crud_daily: {e}")
    print(f"[FAIL] app.crud.crud_daily: {e}")

try:
    from app.tasks.sync_daily import sync_daily_attendance
    print("[PASS] app.tasks.sync_daily")
except Exception as e:
    errors.append(f"[FAIL] app.tasks.sync_daily: {e}")
    print(f"[FAIL] app.tasks.sync_daily: {e}")

# Test 7: Routers
try:
    from app.routers.auth import router as auth_router
    print("[PASS] app.routers.auth")
except Exception as e:
    errors.append(f"[FAIL] app.routers.auth: {e}")
    print(f"[FAIL] app.routers.auth: {e}")

try:
    from app.routers.attendance import router as attendance_router
    print("[PASS] app.routers.attendance")
except Exception as e:
    errors.append(f"[FAIL] app.routers.attendance: {e}")
    print(f"[FAIL] app.routers.attendance: {e}")

try:
    from app.routers.hierarchy import router as hierarchy_router
    print("[PASS] app.routers.hierarchy")
except Exception as e:
    errors.append(f"[FAIL] app.routers.hierarchy: {e}")
    print(f"[FAIL] app.routers.hierarchy: {e}")

try:
    from app.routers.csv_upload import router as csv_router
    print("[PASS] app.routers.csv_upload")
except Exception as e:
    errors.append(f"[FAIL] app.routers.csv_upload: {e}")
    print(f"[FAIL] app.routers.csv_upload: {e}")

# mock_cosec router was a dev-only artifact, removed in production
# try:
#     from app.routers.mock_cosec import router as mock_router
#     print("[PASS] app.routers.mock_cosec")
# except Exception as e:
#     errors.append(f"[FAIL] app.routers.mock_cosec: {e}")
#     print(f"[FAIL] app.routers.mock_cosec: {e}")

# Test 8: Main app
try:
    from app.main import app
    print("[PASS] app.main (FastAPI app)")
except Exception as e:
    errors.append(f"[FAIL] app.main: {e}")
    print(f"[FAIL] app.main: {e}")

# Test 9: CSV parser unit test (updated for new API)
try:
    from app.services.csv_parser import parse_attendance_file, parse_time, parse_work_hours
    from datetime import date

    t = parse_time("09:05:00", date(2026,4,25))
    assert t is not None

    wh = parse_work_hours("09:25:00")
    assert wh is not None

    print("[PASS] CSV parser unit tests")
except Exception as e:
    errors.append(f"[FAIL] CSV parser unit tests: {e}")
    print(f"[FAIL] CSV parser unit tests: {e}")

# Test 10: CSV sync schema
try:
    from app.schemas.csv_sync import CSVAttendanceRowSchema, CSVUploadResult, CSVValidationError
    print("[PASS] app.schemas.csv_sync")
except Exception as e:
    errors.append(f"[FAIL] app.schemas.csv_sync: {e}")
    print(f"[FAIL] app.schemas.csv_sync: {e}")

# Test 11: CSV CRUD
try:
    from app.crud.crud_csv import upsert_csv_batch, upsert_csv_record
    print("[PASS] app.crud.crud_csv")
except Exception as e:
    errors.append(f"[FAIL] app.crud.crud_csv: {e}")
    print(f"[FAIL] app.crud.crud_csv: {e}")

# Test 12: Admin CSV router
try:
    from app.routers.admin_csv import router as admin_csv_router
    print("[PASS] app.routers.admin_csv")
except Exception as e:
    errors.append(f"[FAIL] app.routers.admin_csv: {e}")
    print(f"[FAIL] app.routers.admin_csv: {e}")

# Summary
print(f"\n{'='*50}")
if errors:
    print(f"FAILED: {len(errors)} module(s) have issues")
    for e in errors:
        print(f"  {e}")
else:
    print("ALL TESTS PASSED - All backend modules load correctly")
