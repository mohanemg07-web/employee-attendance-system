import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.config import get_settings

async def main():
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE attendance_logs ADD COLUMN IF NOT EXISTS is_late BOOLEAN DEFAULT FALSE;"))
        print("is_late column added successfully")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
