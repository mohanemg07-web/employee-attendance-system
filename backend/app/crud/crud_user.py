"""
CRUD operations for the ``employees`` table — COSEC User Master sync.

Provides a **two-pass** upsert pipeline that:

Pass 1 — ``upsert_employee_batch()``:
    Insert or update every employee record using ``ON CONFLICT (employee_code)
    DO UPDATE``.  The ``manager_id`` column is left NULL during this pass
    because the manager's internal ``id`` may not exist yet.

Pass 2 — ``link_manager_hierarchy()``:
    After all employees are present in the table, resolve each record's
    ``manager_code`` (from COSEC ``rg_incharge_1`` / ``reporting-incharge``)
    into the internal ``employees.id`` and set ``manager_id``.

This two-pass approach avoids FK violations and ordering dependencies.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.user_sync import (
    UserMasterSyncSchema,
    UserSyncResult,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  Pass 1 — Employee Upsert
# ═══════════════════════════════════════════════════════════

async def upsert_single_employee(
    db: AsyncSession,
    record: UserMasterSyncSchema,
) -> str:
    """
    Upsert a single employee into the ``employees`` table.

    * On insert: creates the row with ``manager_id = NULL``.
    * On conflict: updates ``full_name``, ``email``, ``department``,
      ``role``, ``is_active``.

    The ``email`` column has a UNIQUE constraint, so we handle the
    edge case of employees without an email by generating a
    deterministic placeholder (``<employee_code>@cosec.local``).

    Uses PostgreSQL's ``xmax`` system column to distinguish INSERT
    (``xmax = 0``) from UPDATE (``xmax > 0``).

    Returns:
        ``"inserted"`` or ``"updated"``.
    """
    email = record.best_email or f"{record.employee_code}@cosec.local"
    department = record.department_display
    is_active = record.is_active

    result = await db.execute(
        text("""
            INSERT INTO employees
                (employee_code, email, full_name, role,
                 department, is_active)
            VALUES
                (:code, :email, :name, :role,
                 :dept, :active)
            ON CONFLICT (employee_code)
            DO UPDATE SET
                full_name  = EXCLUDED.full_name,
                email      = CASE
                    -- Preserve a real email over a placeholder
                    WHEN employees.email LIKE '%@cosec.local'
                        THEN EXCLUDED.email
                    WHEN EXCLUDED.email LIKE '%@cosec.local'
                        THEN employees.email
                    ELSE EXCLUDED.email
                END,
                department = EXCLUDED.department,
                role       = EXCLUDED.role,
                is_active  = EXCLUDED.is_active,
                updated_at = NOW()
            RETURNING xmax
        """),
        {
            "code": record.employee_code,
            "email": email,
            "name": record.full_name,
            "role": record.inferred_role,
            "dept": department,
            "active": is_active,
        },
    )

    row = result.fetchone()
    # PostgreSQL: xmax = 0 means INSERT, xmax > 0 means UPDATE
    if row and row[0] == 0:
        return "inserted"
    return "updated"


async def upsert_employee_batch(
    db: AsyncSession,
    records: List[UserMasterSyncSchema],
) -> Tuple[int, int, int, List[str]]:
    """
    Pass 1: Upsert all employees into the database.

    Uses ``begin_nested()`` savepoints so a single row failure does
    not roll back the entire batch.

    Args:
        db: Active async session (caller manages outer transaction).
        records: Pre-validated ``UserMasterSyncSchema`` list.

    Returns:
        ``(inserted, updated, errors, error_messages)`` tuple.
    """
    inserted = 0
    updated = 0
    errors = 0
    error_messages: List[str] = []

    for record in records:
        try:
            # Savepoint per record — a single failure won't abort batch
            async with db.begin_nested():
                outcome = await upsert_single_employee(db, record)
                if outcome == "inserted":
                    inserted += 1
                else:
                    updated += 1
        except Exception as exc:
            errors += 1
            msg = f"Upsert failed for employee {record.employee_code}: {exc}"
            error_messages.append(msg)
            logger.error(msg)

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        msg = f"Pass-1 commit failed: {exc}"
        error_messages.append(msg)
        logger.error(msg)
        errors += 1

    logger.info(
        "Pass 1 complete: inserted=%d updated=%d errors=%d",
        inserted,
        updated,
        errors,
    )
    return inserted, updated, errors, error_messages


# ═══════════════════════════════════════════════════════════
#  Pass 2 — Manager Hierarchy Linking
# ═══════════════════════════════════════════════════════════

async def _build_code_to_id_map(
    db: AsyncSession,
) -> Dict[str, int]:
    """
    Build a lookup dict mapping ``employee_code → employees.id``
    for all employees currently in the database.
    """
    result = await db.execute(
        text("SELECT employee_code, id FROM employees")
    )
    return {row[0]: row[1] for row in result.fetchall()}


async def _identify_managers(
    records: List[UserMasterSyncSchema],
) -> Set[str]:
    """
    Collect all unique employee codes that are referenced as a manager
    by at least one other employee.

    Used to set ``role = 'MANAGER'`` for those employees.
    """
    manager_codes: Set[str] = set()
    for record in records:
        mc = record.manager_code
        if mc:
            manager_codes.add(mc)
    return manager_codes


async def link_manager_hierarchy(
    db: AsyncSession,
    records: List[UserMasterSyncSchema],
) -> Tuple[int, int, List[str]]:
    """
    Pass 2: Resolve ``manager_code`` → ``manager_id`` for every employee
    and update the ``employees`` table to construct the adjacency list.

    Also promotes employees who appear as someone else's manager
    to ``role = 'MANAGER'``.

    Args:
        db: Active async session.
        records: The same validated records from pass 1 (we need their
            ``manager_code`` properties).

    Returns:
        ``(links_set, links_failed, error_messages)`` tuple.
    """
    code_to_id = await _build_code_to_id_map(db)
    manager_codes = await _identify_managers(records)

    links_set = 0
    links_failed = 0
    error_messages: List[str] = []

    for record in records:
        mc = record.manager_code
        if mc is None:
            # No manager assigned → ensure manager_id is NULL
            try:
                await db.execute(
                    text("""
                        UPDATE employees
                        SET manager_id = NULL, updated_at = NOW()
                        WHERE employee_code = :code
                          AND manager_id IS NOT NULL
                    """),
                    {"code": record.employee_code},
                )
            except Exception as exc:
                logger.debug(
                    "Failed to clear manager_id for %s: %s",
                    record.employee_code,
                    exc,
                )
            continue

        manager_internal_id = code_to_id.get(mc)
        if manager_internal_id is None:
            links_failed += 1
            msg = (
                f"Manager code '{mc}' for employee "
                f"'{record.employee_code}' not found in DB."
            )
            error_messages.append(msg)
            logger.warning(msg)
            continue

        try:
            await db.execute(
                text("""
                    UPDATE employees
                    SET manager_id = :mgr_id, updated_at = NOW()
                    WHERE employee_code = :code
                """),
                {
                    "mgr_id": manager_internal_id,
                    "code": record.employee_code,
                },
            )
            links_set += 1
        except Exception as exc:
            links_failed += 1
            msg = (
                f"Failed to set manager_id for {record.employee_code} "
                f"→ {mc} (id={manager_internal_id}): {exc}"
            )
            error_messages.append(msg)
            logger.error(msg)

    # ── Promote managers to role = 'MANAGER' ───────────────
    if manager_codes:
        # Build a parameterised IN clause
        # SQLAlchemy text() doesn't support list params directly,
        # so we build named params dynamically.
        param_names = [f":mc_{i}" for i in range(len(manager_codes))]
        params: Dict[str, str] = {
            f"mc_{i}": code
            for i, code in enumerate(sorted(manager_codes))
        }
        in_clause = ", ".join(param_names)

        try:
            result = await db.execute(
                text(f"""
                    UPDATE employees
                    SET role = 'MANAGER', updated_at = NOW()
                    WHERE employee_code IN ({in_clause})
                      AND role != 'ADMIN'
                """),
                params,
            )
            promoted = result.rowcount
            logger.info(
                "Promoted %d employees to MANAGER role.", promoted
            )
        except Exception as exc:
            logger.error("Failed to promote managers: %s", exc)

    # Commit pass 2
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        msg = f"Pass-2 commit failed: {exc}"
        error_messages.append(msg)
        logger.error(msg)

    logger.info(
        "Pass 2 complete: manager_links_set=%d failed=%d",
        links_set,
        links_failed,
    )
    return links_set, links_failed, error_messages


# ═══════════════════════════════════════════════════════════
#  Full Sync Pipeline
# ═══════════════════════════════════════════════════════════

async def sync_users_full(
    db: AsyncSession,
    records: List[UserMasterSyncSchema],
) -> UserSyncResult:
    """
    Run the full two-pass sync pipeline:

    1. Upsert all employee records (pass 1).
    2. Link manager hierarchy (pass 2).

    Args:
        db: Active async SQLAlchemy session.
        records: Pre-validated ``UserMasterSyncSchema`` list.

    Returns:
        ``UserSyncResult`` with comprehensive counts.
    """
    result = UserSyncResult(
        total_fetched=len(records),
        validated=len(records),
    )

    # ── Pass 1 ─────────────────────────────────────────────
    inserted, updated, errors, err_msgs = await upsert_employee_batch(
        db, records
    )
    result.inserted = inserted
    result.updated = updated
    result.errors = errors
    result.error_messages.extend(err_msgs)

    # ── Pass 2 ─────────────────────────────────────────────
    links_set, links_failed, link_msgs = await link_manager_hierarchy(
        db, records
    )
    result.manager_links_set = links_set
    result.manager_links_failed = links_failed
    result.error_messages.extend(link_msgs)

    logger.info(
        "User sync pipeline complete — "
        "total=%d inserted=%d updated=%d manager_links=%d "
        "link_failures=%d errors=%d",
        result.total_fetched,
        result.inserted,
        result.updated,
        result.manager_links_set,
        result.manager_links_failed,
        result.errors,
    )

    return result
