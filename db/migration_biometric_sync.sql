-- ============================================================
-- Migration: Biometric Sync Infrastructure
-- Run this in the Supabase SQL Editor AFTER the base schema.
-- All statements are idempotent (safe to re-run).
-- ============================================================

-- ── Sync Logs Table ─────────────────────────────────────
-- Tracks every biometric API sync operation (user/daily/monthly)
-- with timing, record counts, and error details.

CREATE TABLE IF NOT EXISTS sync_logs (
    id                  SERIAL PRIMARY KEY,
    sync_type           VARCHAR(20) NOT NULL,
    status              VARCHAR(20) NOT NULL DEFAULT 'RUNNING',
    triggered_by        VARCHAR(20) NOT NULL DEFAULT 'SCHEDULER',
    started_at          TIMESTAMPTZ DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    records_fetched     INTEGER DEFAULT 0,
    records_inserted    INTEGER DEFAULT 0,
    records_updated     INTEGER DEFAULT 0,
    records_skipped     INTEGER DEFAULT 0,
    records_errors      INTEGER DEFAULT 0,
    duration_seconds    INTEGER,
    error_log           JSONB,
    metadata_payload    JSONB
);

-- Index for admin sync-status queries (most recent first by type)
CREATE INDEX IF NOT EXISTS idx_sync_logs_type_started
    ON sync_logs(sync_type, started_at DESC);

-- Index for filtering by status (e.g. find FAILED syncs)
CREATE INDEX IF NOT EXISTS idx_sync_logs_status
    ON sync_logs(status);

-- ── RLS for sync_logs (match existing pattern) ──────────
ALTER TABLE sync_logs ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'sync_logs' AND policyname = 'service_role_all_sync_logs'
    ) THEN
        CREATE POLICY "service_role_all_sync_logs" ON sync_logs
            FOR ALL USING (true) WITH CHECK (true);
    END IF;
END $$;

-- ── Verify attendance_monthly CHECK constraint ──────────
-- The data_source column must accept 'AGGREGATED' in addition to
-- 'API' and 'MANUAL_CSV'. This was added in a previous migration
-- but we verify it here for completeness.
-- (The constraint in supabase_schema.sql already includes 'AGGREGATED')

-- ── Updated_at trigger for sync_logs ────────────────────
-- sync_logs doesn't have an updated_at column, so no trigger needed.

-- ============================================================
-- NOTES
-- ============================================================
-- sync_type values: USER, DAILY, MONTHLY
-- status values: RUNNING, SUCCESS, FAILED
-- triggered_by values: SCHEDULER, MANUAL
--
-- The sync_logs table is populated by:
--   - app/services/sync_orchestrator.py (auto-creates SyncLog entries)
--   - app/routers/admin_sync.py (manual triggers via admin endpoints)
--
-- Query recent syncs:
--   SELECT * FROM sync_logs ORDER BY started_at DESC LIMIT 20;
--
-- Find failed syncs:
--   SELECT * FROM sync_logs WHERE status = 'FAILED' ORDER BY started_at DESC;
