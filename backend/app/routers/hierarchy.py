"""
Hierarchy router — org-chart endpoints for managers.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.employee import Employee
from app.services.hierarchy import (
    get_hierarchy_tree,
    get_subordinate_ids,
    get_direct_reports,
)
from app.utils.security import get_current_user, require_role

router = APIRouter(prefix="/hierarchy", tags=["Hierarchy"])


@router.get("/tree")
async def hierarchy_tree(
    current_user: Employee = Depends(require_role("MANAGER", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the complete org-chart tree under the authenticated manager.
    Returns a nested JSON structure with children arrays.
    """
    tree = await get_hierarchy_tree(db, current_user.id)
    return {"tree": tree}


@router.get("/subordinates")
async def subordinate_ids(
    current_user: Employee = Depends(require_role("MANAGER", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """
    Get flat list of all subordinate employee IDs (recursive).
    Useful for scoping attendance queries.
    """
    ids = await get_subordinate_ids(db, current_user.id, include_self=False)
    return {"manager_id": current_user.id, "subordinate_ids": ids, "count": len(ids)}


@router.get("/direct-reports")
async def direct_reports(
    current_user: Employee = Depends(require_role("MANAGER", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Get immediate direct reports only (depth=1)."""
    reports = await get_direct_reports(db, current_user.id)
    return {"direct_reports": reports, "count": len(reports)}
