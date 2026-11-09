"""Audit trail for administrative actions. Call `record` for anything an admin does that changes
state, and for security events (logins, failed logins, MFA changes)."""

from typing import Any

from sqlalchemy.orm import Session

from app.models.admin import AdminUser, AuditLog

# Keys that must never land in an audit row, whatever a caller passes.
_FORBIDDEN_KEYS = {"password", "new_password", "current_password", "code", "token", "secret", "mfa_secret"}


def _clean(details: dict[str, Any] | None) -> dict[str, Any]:
    if not details:
        return {}
    return {k: v for k, v in details.items() if k.lower() not in _FORBIDDEN_KEYS}


def record(
    db: Session,
    action: str,
    *,
    admin: AdminUser | None = None,
    actor_email: str | None = None,
    resource_type: str | None = None,
    resource_id: object | None = None,
    details: dict[str, Any] | None = None,
    ip: str | None = None,
    commit: bool = True,
) -> AuditLog:
    row = AuditLog(
        admin_id=admin.id if admin else None,
        actor_email=(admin.email if admin else actor_email),
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        details=_clean(details),
        ip=ip,
    )
    db.add(row)
    if commit:
        db.commit()
    return row
