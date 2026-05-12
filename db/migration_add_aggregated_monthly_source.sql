-- Run once on existing PostgreSQL DBs if monthly aggregation fails with
-- CHECK constraint violation on data_source = 'AGGREGATED'.
ALTER TABLE attendance_monthly DROP CONSTRAINT IF EXISTS attendance_monthly_data_source_check;
ALTER TABLE attendance_monthly ADD CONSTRAINT attendance_monthly_data_source_check
    CHECK (data_source IN ('API', 'MANUAL_CSV', 'AGGREGATED'));
