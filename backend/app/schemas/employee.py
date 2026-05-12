"""
Pydantic schemas for employee data.
"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class EmployeeBase(BaseModel):
    employee_code: str
    email: str
    full_name: str
    role: str = "EMPLOYEE"
    department: Optional[str] = None


class EmployeeRead(EmployeeBase):
    id: int
    manager_id: Optional[int] = None
    is_active: bool = True

    class Config:
        from_attributes = True


class EmployeeNode(BaseModel):
    """Hierarchical tree node for org-chart rendering."""
    id: int
    employee_code: str
    full_name: str
    email: str
    role: str
    department: Optional[str] = None
    depth: int = 0
    children: List["EmployeeNode"] = []

    class Config:
        from_attributes = True


# Rebuild for self-reference
EmployeeNode.model_rebuild()
