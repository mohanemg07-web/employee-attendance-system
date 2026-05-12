"""
Hierarchy service — recursive CTE queries for the organisational tree.
Production: PostgreSQL-only.
"""
from typing import List, Dict, Any, Optional
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import _is_sqlite


async def get_subordinate_ids(
    db: AsyncSession,
    manager_id: int,
    include_self: bool = False,
) -> List[int]:
    """
    Fetch all subordinate employee IDs under a manager using a recursive CTE.

    Args:
        db: Async database session.
        manager_id: The manager's employee ID.
        include_self: Whether to include the manager in the result.

    Returns:
        List of employee IDs in the manager's downstream hierarchy.
    """
    depth_condition = "depth >= 0" if include_self else "depth > 0"
    
    query = text(f"""
        WITH RECURSIVE subordinates AS (
            SELECT id, manager_id, 0 AS depth
            FROM employees
            WHERE id = :manager_id

            UNION ALL

            SELECT e.id, e.manager_id, s.depth + 1
            FROM employees e
            INNER JOIN subordinates s ON e.manager_id = s.id
            WHERE e.is_active = :active_val
        )
        SELECT id FROM subordinates
        WHERE {depth_condition}
        ORDER BY depth;
    """)

    result = await db.execute(
        query, {
            "manager_id": manager_id,
            "active_val": 1 if _is_sqlite else True,
        }
    )
    return [row[0] for row in result.fetchall()]


async def get_hierarchy_tree(
    db: AsyncSession,
    manager_id: int,
) -> List[Dict[str, Any]]:
    """
    Fetch the complete org-chart tree under a manager as a flat list
    with depth information, then assemble into a nested structure.

    Returns:
        Nested list of employee dicts with 'children' arrays.
    """
    query = text("""
        WITH RECURSIVE subordinates AS (
            SELECT id, employee_code, full_name, email,
                   manager_id, role, department, 0 AS depth
            FROM employees
            WHERE id = :manager_id

            UNION ALL

            SELECT e.id, e.employee_code, e.full_name, e.email,
                   e.manager_id, e.role, e.department, s.depth + 1
            FROM employees e
            INNER JOIN subordinates s ON e.manager_id = s.id
            WHERE e.is_active = :active_val
        )
        SELECT id, employee_code, full_name, email,
               manager_id, role, department, depth
        FROM subordinates
        ORDER BY depth, full_name;
    """)

    result = await db.execute(query, {
        "manager_id": manager_id,
        "active_val": 1 if _is_sqlite else True,
    })
    rows = result.fetchall()

    # Build nested tree from flat list
    nodes_by_id: Dict[int, Dict[str, Any]] = {}
    root_children: List[Dict[str, Any]] = []

    for row in rows:
        node = {
            "id": row[0],
            "employee_code": row[1],
            "full_name": row[2],
            "email": row[3],
            "manager_id": row[4],
            "role": row[5],
            "department": row[6],
            "depth": row[7],
            "children": [],
        }
        nodes_by_id[node["id"]] = node

        if node["id"] == manager_id:
            root_children.append(node)
        elif node["manager_id"] in nodes_by_id:
            nodes_by_id[node["manager_id"]]["children"].append(node)

    return root_children


async def get_direct_reports(
    db: AsyncSession,
    manager_id: int,
) -> List[Dict[str, Any]]:
    """Fetch only the immediate direct reports (depth=1) of a manager."""
    query = text("""
        SELECT id, employee_code, full_name, email, role, department
        FROM employees
        WHERE manager_id = :manager_id AND is_active = :active_val
        ORDER BY full_name;
    """)
    result = await db.execute(query, {
        "manager_id": manager_id,
        "active_val": 1 if _is_sqlite else True,
    })
    return [
        {
            "id": r[0],
            "employee_code": r[1],
            "full_name": r[2],
            "email": r[3],
            "role": r[4],
            "department": r[5],
        }
        for r in result.fetchall()
    ]


async def get_direct_managers(
    db: AsyncSession,
    employee_ids: List[int],
) -> List[int]:
    """
    Fetch the unique manager IDs for a given list of employees.
    Used for cache invalidation.
    """
    if not employee_ids:
        return []
    
    from app.models.employee import Employee
    query = select(Employee.manager_id).where(
        Employee.id.in_(employee_ids),
        Employee.manager_id.isnot(None)
    ).distinct()
    
    result = await db.execute(query)
    return [row[0] for row in result.fetchall()]
