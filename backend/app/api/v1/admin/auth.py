from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.admin_deps import AdminContext, AdminSessionDep
from app.api.deps import DB, client_ip, user_agent
from app.core import rate_limit, security
from app.core.admin_permissions import ROLE_LABELS
from app.core.config import get_settings
from app.db.base import utcnow
from app.schemas.admin import (
    AdminChangePasswordIn,
    AdminCodeIn,
    AdminLoginIn,
    AdminMe,
    AdminMfaChallengeOut,
    AdminMfaDisableIn,
    AdminMfaSetupOut,
    AdminMfaVerifyIn,
    AdminSessionOut,
)
from app.services import admin_auth, audit

router = APIRouter(prefix="/auth", tags=["admin: auth"])

MIN15 = 15 * 60


def me_out(ctx: AdminContext) -> AdminMe:
    a = ctx.admin
    return AdminMe(
        id=a.id, email=a.email, full_name=a.full_name, role=a.role, role_label=ROLE_LABELS[a.role],
        permissions=sorted(ctx.permissions), mfa_enabled=a.mfa_enabled_at is not None,
        mfa_required=get_settings().admin_mfa_required, mfa_setup_needed=ctx.mfa_setup_needed,
        last_login_at=a.last_login_at,
    )


def _session_out(issued: admin_auth.IssuedSession, ctx: AdminContext) -> AdminSessionOut:
    return AdminSessionOut(token=issued.token, expires_at=issued.session.expires_at,
                           idle_timeout_minutes=get_settings().admin_session_idle_minutes, admin=me_out(ctx))


def _bad_code() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, {"code": "invalid_mfa_code", "message": "That code isn't right."})


@router.post("/login", response_model=AdminSessionOut | AdminMfaChallengeOut)
def login(data: AdminLoginIn, request: Request, db: DB):
    email = admin_auth.normalise_email(data.email)
    ip = client_ip(request)
    rate_limit.hit(db, f"admin-login:ip:{ip}", limit=20, window_seconds=MIN15)
    rate_limit.hit(db, f"admin-login:email:{email}", limit=5, window_seconds=MIN15)
    admin = admin_auth.authenticate(db, email, data.password, ip=ip)
    rate_limit.reset(db, f"admin-login:email:{email}")

    if admin.mfa_enabled_at is not None:
        audit.record(db, "admin.login_password_ok", admin=admin, ip=ip)
        return AdminMfaChallengeOut(mfa_token=admin_auth.make_mfa_challenge(admin))

    issued = admin_auth.create_session(db, admin, mfa_verified=False, ip=ip, user_agent=user_agent(request))
    audit.record(db, "admin.login", admin=admin, details={"mfa": False}, ip=ip)
    return _session_out(issued, AdminContext(admin=admin, session=issued.session))


@router.post("/mfa/verify", response_model=AdminSessionOut)
def verify_mfa(data: AdminMfaVerifyIn, request: Request, db: DB):
    ip = client_ip(request)
    admin = admin_auth.read_mfa_challenge(db, data.mfa_token)
    rate_limit.hit(db, f"admin-mfa:admin:{admin.id}", limit=5, window_seconds=MIN15)
    if not admin_auth.check_totp(db, admin, data.code):
        audit.record(db, "admin.login_failed", admin=admin, details={"reason": "bad_mfa_code"}, ip=ip)
        raise _bad_code()
    rate_limit.reset(db, f"admin-mfa:admin:{admin.id}")
    issued = admin_auth.create_session(db, admin, mfa_verified=True, ip=ip, user_agent=user_agent(request))
    audit.record(db, "admin.login", admin=admin, details={"mfa": True}, ip=ip)
    return _session_out(issued, AdminContext(admin=admin, session=issued.session))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(ctx: AdminSessionDep, request: Request, db: DB):
    admin_auth.revoke_session(db, ctx.session)
    audit.record(db, "admin.logout", admin=ctx.admin, ip=client_ip(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=AdminMe)
def me(ctx: AdminSessionDep):
    return me_out(ctx)


@router.post("/mfa/setup", response_model=AdminMfaSetupOut)
def mfa_setup(ctx: AdminSessionDep, request: Request, db: DB):
    """Start (or restart) enrolment. The secret is shown once; it becomes active after /mfa/enable."""
    rate_limit.hit(db, f"admin-mfa-setup:admin:{ctx.admin.id}", limit=10, window_seconds=MIN15)
    secret, uri = admin_auth.start_mfa_enrolment(db, ctx.admin)
    return AdminMfaSetupOut(secret=secret, otpauth_uri=uri)


@router.post("/mfa/enable", response_model=AdminMe)
def mfa_enable(data: AdminCodeIn, ctx: AdminSessionDep, request: Request, db: DB):
    admin = ctx.admin
    if admin.mfa_enabled_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            {"code": "mfa_already_enabled", "message": "Two-step verification is already on."})
    if admin.mfa_secret_enc is None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            {"code": "mfa_setup_not_started", "message": "Start setup first."})
    rate_limit.hit(db, f"admin-mfa:admin:{admin.id}", limit=5, window_seconds=MIN15)
    if not admin_auth.check_totp(db, admin, data.code):
        raise _bad_code()
    admin.mfa_enabled_at = utcnow()
    ctx.session.mfa_verified = True
    db.commit()
    # Other sessions were opened without the second factor: end them.
    admin_auth.revoke_all(db, admin, except_id=ctx.session.id)
    audit.record(db, "admin.mfa_enabled", admin=admin, resource_type="admin_user", resource_id=admin.id,
                 ip=client_ip(request))
    return me_out(ctx)


@router.post("/mfa/disable", response_model=AdminMe)
def mfa_disable(data: AdminMfaDisableIn, ctx: AdminSessionDep, request: Request, db: DB):
    admin = ctx.admin
    if get_settings().admin_mfa_required:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            {"code": "mfa_required", "message": "Two-step verification is required on this server."})
    if admin.mfa_enabled_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, {"code": "mfa_not_enabled", "message": "It isn't on."})
    rate_limit.hit(db, f"admin-mfa:admin:{admin.id}", limit=5, window_seconds=MIN15)
    if not security.verify_password(data.password, admin.password_hash) or not admin_auth.check_totp(db, admin, data.code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            {"code": "invalid_credentials", "message": "Password or code is incorrect."})
    admin.mfa_enabled_at = None
    admin.mfa_secret_enc = None
    admin.mfa_last_step = None
    ctx.session.mfa_verified = False
    db.commit()
    audit.record(db, "admin.mfa_disabled", admin=admin, resource_type="admin_user", resource_id=admin.id,
                 ip=client_ip(request))
    return me_out(ctx)


@router.post("/change-password", response_model=AdminSessionOut)
def change_password(data: AdminChangePasswordIn, ctx: AdminSessionDep, request: Request, db: DB):
    admin = ctx.admin
    ip = client_ip(request)
    rate_limit.hit(db, f"admin-change-pw:admin:{admin.id}", limit=5, window_seconds=MIN15)
    if not security.verify_password(data.current_password, admin.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            {"code": "invalid_credentials", "message": "Current password is incorrect."})
    admin_auth.validate_new_password(data.new_password, email=admin.email)
    admin.password_hash = security.hash_password(data.new_password)
    admin.password_changed_at = utcnow()
    db.commit()
    # Every existing session (this one included) predates the change: issue a fresh one.
    admin_auth.revoke_all(db, admin)
    issued = admin_auth.create_session(db, admin, mfa_verified=ctx.session.mfa_verified, ip=ip,
                                       user_agent=user_agent(request))
    audit.record(db, "admin.password_changed", admin=admin, resource_type="admin_user", resource_id=admin.id, ip=ip)
    return _session_out(issued, AdminContext(admin=admin, session=issued.session))
