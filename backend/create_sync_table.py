"""Create sync_logs table in PostgreSQL."""
import asyncio

async def create():
    from app.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "CREATE TABLE IF NOT EXISTS sync_logs ("
            "  id SERIAL PRIMARY KEY,"
            "  sync_type VARCHAR(20) NOT NULL,"
            "  status VARCHAR(20) NOT NULL DEFAULT 'RUNNING',"
            "  triggered_by VARCHAR(20) NOT NULL DEFAULT 'SCHEDULER',"
            "  started_at TIMESTAMPTZ DEFAULT NOW(),"
            "  completed_at TIMESTAMPTZ,"
            "  records_fetched INTEGER DEFAULT 0,"
            "  records_inserted INTEGER DEFAULT 0,"
            "  records_updated INTEGER DEFAULT 0,"
            "  records_skipped INTEGER DEFAULT 0,"
            "  records_errors INTEGER DEFAULT 0,"
            "  duration_seconds INTEGER,"
            "  error_log JSONB,"
            "  metadata_payload JSONB"
            ")"
        ))
        await db.commit()
        r = await db.execute(text("SELECT count(*) FROM sync_logs"))
        print("sync_logs table created OK, rows:", r.scalar())

asyncio.run(create())
