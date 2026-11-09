"""Dependencies for /api/v1/admin. Every admin route must depend on `require_permission(...)`
(or, for the few self-service auth routes, `AdminSessionDep`). Mobile-app tokens are never accepted."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.deps import DB
from app.core.admin_permissions import has_permission, permissions_for
from app.core.config import get_settings
from app.models.admin import AdminSession, AdminUser
from app.services import admin_auth

_bearer = HTTPBearer(auto_error=False)


@dataclass
class AdminContext:
    admin: AdminUser
    session: AdminSession

    @property
    def permissions(self) -> frozenset[str]:
        return permissions_for(self.admin.role)

    def can(self, permission: str) -> bool:
        return has_permission(self.admin.role, permission)

    @property
    def mfa_setup_needed(self) -> bool:
        return get_settings().admin_mfa_required and not self.session.mfa_verified


def _unauthorized(message: str = "Please sign in.") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, {"code": "admin_not_authenticated", "message": message},
                         headers={"WWW-Authenticate": "Bearer"})


def current_admin(db: DB, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> AdminContext:
    if creds is None:
        raise _unauthorized()
    resolved = admin_auth.resolve_session(db, creds.credentials)
    if resolved is None:
        raise _unauthorized("Your session has ended. Please sign in again.")
    session, admin = resolved
    return AdminContext(admin=admin, session=session)


AdminSessionDep = Annotated[AdminContext, Depends(current_admin)]


def require_permission(permission: str):
    has_permission("owner", permission)  # validates the name at import time: typos fail on startup

    def dependency(ctx: AdminSessionDep) -> AdminContext:
        if ctx.mfa_setup_needed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, {
                "code": "mfa_setup_required", "message": "Set up two-step verification to continue."})
        if not ctx.can(permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, {
                "code": "forbidden", "message": "Your role doesn't allow this action."})
        return ctx

    return dependency


def Permission(permission: str):
    """Annotated dependency: `ctx: Permission("users.read")`."""
    return Annotated[AdminContext, Depends(require_permission(permission))]
