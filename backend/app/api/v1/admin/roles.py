from fastapi import APIRouter
from pydantic import BaseModel

from app.api.admin_deps import Permission
from app.core.admin_permissions import PERMISSIONS, ROLE_LABELS, ROLE_PERMISSIONS

router = APIRouter(prefix="/roles", tags=["admin: roles"])


class RoleOut(BaseModel):
    key: str
    label: str
    permissions: list[str]


class RolesOut(BaseModel):
    roles: list[RoleOut]
    permissions: dict[str, str]


@router.get("", response_model=RolesOut)
def list_roles(_: Permission("admins.manage")):
    """The role → permission matrix the backend enforces (read-only; roles are defined in code)."""
    return RolesOut(
        roles=[RoleOut(key=k, label=ROLE_LABELS[k], permissions=sorted(v)) for k, v in ROLE_PERMISSIONS.items()],
        permissions=PERMISSIONS,
    )
