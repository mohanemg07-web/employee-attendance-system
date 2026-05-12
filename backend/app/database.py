"""
Async SQLAlchemy engine, session factory, and FastAPI dependency.

Production: Supabase PostgreSQL with PgBouncer transaction-mode pooling.
Local dev:  SQLite via aiosqlite (set DATABASE_URL=sqlite+aiosqlite:///./dev.db)
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

_db_url = settings.DATABASE_URL
_is_sqlite = _db_url.startswith("sqlite")

if _is_sqlite:
    # SQLite — no pooling args, no connect_args
    engine = create_async_engine(_db_url, echo=False)
else:
    # PostgreSQL (Supabase PgBouncer transaction mode)
    engine = create_async_engine(
        _db_url,
        echo=False,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        connect_args={
            "prepared_statement_cache_size": 0,
            "statement_cache_size": 0,
        },
    )

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


async def init_db():
    """Create all tables (used for SQLite dev mode)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    """FastAPI dependency that yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
