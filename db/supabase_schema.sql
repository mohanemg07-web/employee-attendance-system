-- ============================================================
-- Supabase PostgreSQL Schema — Employee Attendance Dashboard
-- Run this in the Supabase SQL Editor (Dashboard → SQL Editor)
-- ============================================================

-- ── Employees Table (Adjacency List Hierarchy) ──────────
CREATE TABLE IF NOT EXISTS employees (
    id              SERIAL PRIMARY KEY,
    employee_code   VARCHAR(50) UNIQUE NOT NULL,
    email           VARCHAR(255) UNIQUE NOT NULL,
    full_name       VARCHAR(255) NOT NULL,
    role            VARCHAR(20) NOT NULL DEFAULT 'EMPLOYEE'
                    CHECK (role IN ('EMPLOYEE', 'MANAGER', 'ADMIN')),
    manager_id      INT REFERENCES employees(id) ON DELETE SET NULL,
    department      VARCHAR(100),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_employees_code ON employees(employee_code);
CREATE INDEX IF NOT EXISTS idx_employees_email ON employees(email);
CREATE INDEX IF NOT EXISTS idx_employees_manager ON employees(manager_id);

-- ── Daily Attendance Logs ───────────────────────────────
CREATE TABLE IF NOT EXISTS attendance_logs (
    id              SERIAL PRIMARY KEY,
    employee_id     INT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    log_date        DATE NOT NULL,
    first_in        TIMESTAMPTZ,
    last_out        TIMESTAMPTZ,
    gross_work_hrs  INTERVAL,
    net_work_hrs    INTERVAL,
    status          VARCHAR(30) DEFAULT 'PRESENT',
    is_late         BOOLEAN DEFAULT FALSE,
    data_source     VARCHAR(20) NOT NULL DEFAULT 'API'
                    CHECK (data_source IN ('API', 'MANUAL_CSV')),
    raw_payload     JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_employee_log_date UNIQUE (employee_id, log_date)
);

CREATE INDEX IF NOT EXISTS idx_attendance_empid ON attendance_logs(employee_id);
CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance_logs(log_date);
CREATE INDEX IF NOT EXISTS idx_attendance_source ON attendance_logs(data_source);
CREATE INDEX IF NOT EXISTS idx_logs_emp_date ON attendance_logs(employee_id, log_date);

-- ── Monthly Attendance Summaries ────────────────────────
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

    CONSTRAINT uq_employee_month_year UNIQUE (employee_id, month, year)
);

CREATE INDEX IF NOT EXISTS idx_monthly_emp_month_year ON attendance_monthly(employee_id, month, year);

-- ── Audit Logs ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
    id              SERIAL PRIMARY KEY,
    user_id         INT REFERENCES employees(id) ON DELETE SET NULL,
    action          VARCHAR(100) NOT NULL,
    timestamp       TIMESTAMPTZ DEFAULT NOW(),
    metadata_payload JSONB
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user   ON audit_logs(user_id);

-- ── Disable Supabase RLS (backend handles auth via JWT) ─
ALTER TABLE employees ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendance_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendance_monthly ENABLE ROW LEVEL SECURITY;

-- Allow full access for the service role (backend connection)
CREATE POLICY "service_role_all_employees" ON employees
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all_attendance" ON attendance_logs
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all_monthly" ON attendance_monthly
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all_audit" ON audit_logs
    FOR ALL USING (true) WITH CHECK (true);


-- ============================================================
-- NOTES
-- ============================================================
-- Employees are managed externally (admin UI or direct DB insert).
-- No demo/seed data is inserted by this schema.
-- Attendance data is populated via CSV upload or COSEC API sync.


-- ============================================================
-- FUNCTIONS — Recursive Hierarchy CTE
-- ============================================================

-- Return all subordinates (direct + nested) under a given manager.
-- Useful for Supabase RPC or direct SQL queries from the dashboard.
CREATE OR REPLACE FUNCTION get_subordinates(root_id INT)
RETURNS TABLE (
    id              INT,
    employee_code   VARCHAR,
    full_name       VARCHAR,
    email           VARCHAR,
    role            VARCHAR,
    department      VARCHAR,
    manager_id      INT,
    depth           INT
) AS $$
    WITH RECURSIVE subordinates AS (
        -- Anchor: the root manager
        SELECT e.id, e.employee_code, e.full_name, e.email,
               e.role, e.department, e.manager_id, 0 AS depth
        FROM employees e
        WHERE e.id = root_id

        UNION ALL

        -- Recursive: all active direct reports
        SELECT e.id, e.employee_code, e.full_name, e.email,
               e.role, e.department, e.manager_id, s.depth + 1
        FROM employees e
        INNER JOIN subordinates s ON e.manager_id = s.id
        WHERE e.is_active = TRUE
    )
    SELECT * FROM subordinates
    ORDER BY depth, full_name;
$$ LANGUAGE SQL STABLE;

COMMENT ON FUNCTION get_subordinates IS
    'Recursive CTE returning the full org tree under a manager. '
    'Depth 0 = the manager, depth 1 = direct reports, etc.';


-- ============================================================
-- TRIGGER — Auto-update updated_at on row changes
-- ============================================================

CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_employees_updated'
    ) THEN
        CREATE TRIGGER trg_employees_updated
            BEFORE UPDATE ON employees
            FOR EACH ROW EXECUTE FUNCTION update_modified_column();
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_attendance_logs_updated'
    ) THEN
        CREATE TRIGGER trg_attendance_logs_updated
            BEFORE UPDATE ON attendance_logs
            FOR EACH ROW EXECUTE FUNCTION update_modified_column();
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_attendance_monthly_updated'
    ) THEN
        CREATE TRIGGER trg_attendance_monthly_updated
            BEFORE UPDATE ON attendance_monthly
            FOR EACH ROW EXECUTE FUNCTION update_modified_column();
    END IF;
END $$;
