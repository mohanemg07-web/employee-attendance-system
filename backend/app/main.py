# reload-trigger-v4
"""
FastAPI application factory — Employee Attendance Tracking Dashboard.
Production: PostgreSQL via Supabase. Local dev: SQLite with auto-init.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


from app.config import get_settings
from app.database import _is_sqlite
from app.routers import auth, attendance, hierarchy, csv_upload, admin_csv, admin_sync
from app.utils.logging_setup import setup_json_logging

# Configure structured JSON logging globally
setup_json_logging()

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle. Creates tables, starts scheduler."""
    if _is_sqlite:
        await _init_sqlite()

    # Start biometric sync scheduler if enabled
    scheduler = None
    if settings.BIOMETRIC_SYNC_ENABLED:
        try:
            from app.services.sync_scheduler import start_scheduler
            scheduler = start_scheduler()
            print("[INIT] Biometric sync scheduler started")
        except Exception as exc:
            print(f"[INIT] Scheduler start failed: {exc}")
    else:
        print("[INIT] Biometric sync scheduler disabled (BIOMETRIC_SYNC_ENABLED=false)")

    yield

    # Shutdown scheduler gracefully
    if scheduler:
        try:
            from app.services.sync_scheduler import stop_scheduler
            stop_scheduler()
        except Exception:
            pass


async def _init_sqlite():
    """Create tables for SQLite dev mode. No demo data is inserted."""
    from app.database import init_db

    await init_db()
    print("[INIT] SQLite tables created (no seed data)")


app = FastAPI(
    title="Employee Attendance Dashboard",
    description="Secure attendance tracking with enterprise auth, hierarchy, and COSEC integration",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── Middleware ──────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
        "https://employee-attendance-system-pearl.vercel.app",
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# ── Routers ────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(attendance.router)
app.include_router(hierarchy.router)
app.include_router(csv_upload.router)
app.include_router(admin_csv.router)
app.include_router(admin_sync.router)


@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok", "service": "Employee Attendance Dashboard API"}


from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db

@app.get("/health", tags=["Health"])
async def health(db: AsyncSession = Depends(get_db)):
    """Health check endpoint validating PostgreSQL and Redis connections."""
    status_code = 200
    db_status = "failed"
    redis_status = "failed"

    # Ping Database
    try:
        await db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        status_code = 503

    # Ping Redis
    try:
        from app.services.cache import get_redis
        redis_client = get_redis()
        if redis_client:
            await redis_client.ping()
            redis_status = "connected"
        else:
            redis_status = "not_configured"
    except Exception:
        status_code = 503

    if status_code != 200:
        from fastapi import Response
        import json
        return Response(
            content=json.dumps({"status": "error", "database": db_status, "redis": redis_status}),
            status_code=status_code,
            media_type="application/json"
        )

    return {"status": "ok", "database": db_status, "redis": redis_status}
