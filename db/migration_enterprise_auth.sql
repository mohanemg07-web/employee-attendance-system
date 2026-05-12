-- ============================================================
-- Migration: Enterprise Authentication
-- Run this in the Supabase SQL Editor AFTER the base schema.
-- All statements are idempotent (safe to re-run).
-- ============================================================

-- ── Add authentication columns to employees ────────────
ALTER TABLE employees ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);
ALTER TABLE employees ADD COLUMN IF NOT EXISTS last_login TIMESTAMPTZ;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS password_reset_required BOOLEAN DEFAULT true;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER DEFAULT 0;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS account_locked_until TIMESTAMPTZ;

-- ── Set default password for all existing employees ────
-- bcrypt hash of "Admin@123" (cost factor 12)
-- Generated via: python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('Admin@123'))"
-- IMPORTANT: Run this ONCE after migration. All users must change their password on first login.

-- You can generate the hash and UPDATE manually, or use the seed_passwords.py script.
-- Example (replace $HASH with actual bcrypt output):
--
--   UPDATE employees
--   SET password_hash = '$2b$12$...',
--       password_reset_required = true
--   WHERE password_hash IS NULL;

-- ============================================================
-- NOTES
-- ============================================================
-- After running this migration:
-- 1. Run the backend seed script to set initial passwords:
--      python -c "
--      import asyncio
--      from app.database import AsyncSessionLocal
--      from app.models.employee import Employee
--      from app.utils.security import hash_password
--      from sqlalchemy import select, update
--
--      async def seed():
--          async with AsyncSessionLocal() as db:
--              h = hash_password('Admin@123')
--              await db.execute(
--                  update(Employee)
--                  .where(Employee.password_hash == None)
--                  .values(password_hash=h, password_reset_required=True)
--              )
--              await db.commit()
--              print('Passwords seeded successfully')
--
--      asyncio.run(seed())
--      "
--
-- 2. All employees will be required to change their password on first login.
-- 3. The default password is "Admin@123" — communicate this securely.
