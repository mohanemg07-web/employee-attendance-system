"""
Run the enterprise auth migration — adds authentication columns to the employees table.
Then seeds default passwords for all employees.

Uses raw asyncpg (bypasses SQLAlchemy) for PgBouncer compatibility.

Run from the backend directory:
    python -m app.migrate_auth
"""
import asyncio
import re
import os
import sys

# Load .env manually so we don't import app modules that trigger SQLAlchemy engine creation
from dotenv import load_dotenv
load_dotenv()


def _get_asyncpg_dsn():
    """Convert SQLAlchemy DSN to plain asyncpg DSN."""
    url = os.getenv("DATABASE_URL", "")
    # postgresql+asyncpg://... -> postgresql://...
    return re.sub(r"^postgresql\+asyncpg://", "postgresql://", url)


MIGRATION_STATEMENTS = [
    "ALTER TABLE employees ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)",
    "ALTER TABLE employees ADD COLUMN IF NOT EXISTS last_login TIMESTAMPTZ",
    "ALTER TABLE employees ADD COLUMN IF NOT EXISTS password_reset_required BOOLEAN DEFAULT true",
    "ALTER TABLE employees ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER DEFAULT 0",
    "ALTER TABLE employees ADD COLUMN IF NOT EXISTS account_locked_until TIMESTAMPTZ",
]


async def run_migration():
    import asyncpg
    from passlib.context import CryptContext

    dsn = _get_asyncpg_dsn()
    if not dsn:
        print("[ERROR] DATABASE_URL not set in .env")
        sys.exit(1)

    print(f"[MIGRATE] Connecting to database...")
    conn = await asyncpg.connect(dsn, statement_cache_size=0)

    try:
        # Step 1: Run migration DDL
        print("[MIGRATE] Adding authentication columns to employees table...")
        for stmt in MIGRATION_STATEMENTS:
            await conn.execute(stmt)
        print("[MIGRATE] Columns added successfully.")

        # Step 2: Seed default passwords
        print("[SEED] Setting default passwords for employees without one...")
        default_pw = os.getenv("DEFAULT_ADMIN_PASSWORD", "Admin@123")

        pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        hashed = pwd_ctx.hash(default_pw)

        rows = await conn.fetch(
            "SELECT id, employee_code, full_name FROM employees WHERE password_hash IS NULL"
        )

        if not rows:
            print("[SEED] All employees already have passwords set.")
            return

        await conn.execute(
            "UPDATE employees SET password_hash = $1, password_reset_required = true "
            "WHERE password_hash IS NULL",
            hashed,
        )

        print(f"[SEED] Set default password for {len(rows)} employee(s).")
        print(f"[SEED] Default password: {default_pw}")
        print(f"[SEED] All users will be required to change their password on first login.")
        for row in rows:
            print(f"  -> {row['employee_code']} ({row['full_name']})")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_migration())
