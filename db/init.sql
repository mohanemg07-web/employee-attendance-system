-- ============================================================
-- Employee Attendance Tracking Dashboard — Database Schema
-- PostgreSQL 16+
-- ============================================================

-- ============================================================
-- 1. EMPLOYEES  (Adjacency List for organisational hierarchy)
-- ============================================================
CREATE TABLE IF NOT EXISTS employees (
    id              SERIAL PRIMARY KEY,
    employee_code   VARCHAR(50)  UNIQUE NOT NULL,
    email           VARCHAR(255) UNIQUE NOT NULL,
    full_name       VARCHAR(255) NOT NULL,
    role            VARCHAR(20)  NOT NULL DEFAULT 'EMPLOYEE'
                    CHECK (role IN ('EMPLOYEE', 'MANAGER', 'ADMIN')),
    manager_id      INT REFERENCES employees(id) ON DELETE SET NULL,
    department      VARCHAR(100),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_employees_manager ON employees(manager_id);
CREATE INDEX IF NOT EXISTS idx_employees_email   ON employees(email);

-- ============================================================
-- 2. ATTENDANCE LOGS  (daily records with data-source provenance)
-- ============================================================
CREATE TABLE IF NOT EXISTS attendance_logs (
    id              SERIAL PRIMARY KEY,
    employee_id     INT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    log_date        DATE NOT NULL,
    first_in        TIMESTAMPTZ,
    last_out        TIMESTAMPTZ,
    gross_work_hrs  INTERVAL,
    net_work_hrs    INTERVAL,
    status          VARCHAR(30) DEFAULT 'PRESENT'
                    CHECK (status IN (
                        'PRESENT', 'ABSENT', 'HALF_DAY',
                        'LATE', 'ON_LEAVE', 'WEEKEND', 'HOLIDAY'
                    )),
    is_late         BOOLEAN DEFAULT FALSE,
    data_source     VARCHAR(20) NOT NULL DEFAULT 'API'
                    CHECK (data_source IN ('API', 'MANUAL_CSV')),
    raw_payload     JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (employee_id, log_date)
);

CREATE INDEX IF NOT EXISTS idx_attendance_emp_date ON attendance_logs(employee_id, log_date);
CREATE INDEX IF NOT EXISTS idx_attendance_date     ON attendance_logs(log_date);
CREATE INDEX IF NOT EXISTS idx_attendance_source   ON attendance_logs(data_source);

-- ============================================================
-- 3. MONTHLY ATTENDANCE SUMMARY
-- ============================================================
CREATE TABLE IF NOT EXISTS attendance_monthly (
    id              SERIAL PRIMARY KEY,
    employee_id     INT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    month           INT NOT NULL CHECK (month BETWEEN 1 AND 12),
    year            INT NOT NULL,
    total_present   INT DEFAULT 0,
    total_absent    INT DEFAULT 0,
    total_late      INT DEFAULT 0,
    total_half_day  INT DEFAULT 0,
    total_leave     INT DEFAULT 0,
    avg_work_hrs    INTERVAL,
    data_source     VARCHAR(20) NOT NULL DEFAULT 'API'
                    CHECK (data_source IN ('API', 'MANUAL_CSV', 'AGGREGATED')),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (employee_id, month, year)
);

CREATE INDEX IF NOT EXISTS idx_monthly_emp ON attendance_monthly(employee_id);

-- ============================================================
-- 4. NOTES
-- ============================================================
-- Employees are managed externally (admin UI or direct DB insert).
-- No demo/seed data is inserted by this schema.
-- Attendance data is populated via CSV upload or COSEC API sync.
