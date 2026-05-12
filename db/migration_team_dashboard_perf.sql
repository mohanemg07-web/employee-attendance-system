-- ============================================================
-- Migration: Team Dashboard Performance Index
-- Run this in the Supabase SQL Editor
-- ============================================================

-- Covering index for team dashboard monthly queries.
-- The team dashboard filters on (employee_id IN (...), log_date BETWEEN ..., status NOT IN (...))
-- This composite index eliminates the table lookup for status filtering.
CREATE INDEX IF NOT EXISTS idx_logs_emp_date_status 
ON attendance_logs(employee_id, log_date, status);

-- Verify the index was created
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename = 'attendance_logs' 
ORDER BY indexname;
