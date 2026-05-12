"""
Seed script — Set default passwords for all employees without one.
Run from the backend directory:
    python -m app.seed_passwords
"""
import asyncio
import sys

from sqlalchemy import select, update

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.employee import Employee
from app.utils.security import hash_password

settings = get_settings()


async def seed_passwords():
    """Set default password for all employees that don't have one yet."""
    default_pw = settings.DEFAULT_ADMIN_PASSWORD
    hashed = hash_password(default_pw)

    async with AsyncSessionLocal() as db:
        # Count employees without passwords
        result = await db.execute(
            select(Employee).where(Employee.password_hash == None)
        )
        employees = result.scalars().all()

        if not employees:
            print("[SEED] All employees already have passwords set.")
            return

        # Set default password
        await db.execute(
            update(Employee)
            .where(Employee.password_hash == None)
            .values(password_hash=hashed, password_reset_required=True)
        )
        await db.commit()

        print(f"[SEED] Set default password for {len(employees)} employee(s).")
        print(f"[SEED] Default password: {default_pw}")
        print(f"[SEED] All users will be required to change their password on first login.")
        for emp in employees:
            print(f"  → {emp.employee_code} ({emp.full_name})")


if __name__ == "__main__":
    asyncio.run(seed_passwords())
