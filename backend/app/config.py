"""
Application settings loaded from environment variables.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── Database ─────────────────────────────────
    # Defaults to SQLite for local dev. Override with Supabase URL in production.
    DATABASE_URL: str = "sqlite+aiosqlite:///./attendance_dev.db"

    # ── Redis (Render Redis or Upstash) ─────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Enterprise Auth ──────────────────────────
    DEFAULT_ADMIN_PASSWORD: str = "Admin@123"
    MAX_LOGIN_ATTEMPTS: int = 5
    ACCOUNT_LOCKOUT_MINUTES: int = 15

    # ── JWT ──────────────────────────────────────
    JWT_SECRET_KEY: str = "dev-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ── Matrix COSEC API ────────────────────────
    MATRIX_COSEC_BASE_URL: str = ""
    MATRIX_COSEC_USERNAME: str = "SA"
    MATRIX_COSEC_PASSWORD: str = ""

    # ── Caching ─────────────────────────────────
    LIVE_CACHE_TTL_MINUTES: int = 15

    # ── Biometric Sync ─────────────────────────
    SYNC_INTERVAL_MINUTES: int = 15
    BIOMETRIC_SYNC_ENABLED: bool = False  # Enable background scheduler

    # ── Frontend ────────────────────────────────
    FRONTEND_URL: str = "http://localhost:5173"

    # ── Deployment ──────────────────────────────
    PORT: int = 8000
    DEMO_MODE: bool = False   # Demo mode removed; production only

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
