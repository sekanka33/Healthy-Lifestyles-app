"""Admin authentication: password (Argon2id) + optional/required TOTP, opaque server-side sessions.

Admin tokens look like `lpa_<random>` and are looked up by SHA-256 in `admin_sessions`, so they are
revocable at once and can't be confused with the mobile app's JWTs (different format, different table).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import crypto, security, totp
from app.core.config import get_settings
from app.db.base import as_utc, utcnow
from app.models.admin import AdminSession, AdminUser
from app.services import audit

TOKEN_PREFIX = "lpa_"
MFA_AUDIENCE = "lifepulse-admin-mfa"
MFA_CHALLENGE_TTL = timedelta(minutes=5)
LAST_SEEN_RESOLUTION = timedelta(seconds=60)  # don't write on every request
MIN_PASSWORD_LENGTH = 12


def normalise_email(email: str) -> str:
    return email.strip().lower()


def _invalid_credentials() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED,
                         {"code": "invalid_credentials", "message": "Email or password is incorrect."})


def authenticate(db: Session, email: str, password: str, *, ip: str | None) -> AdminUser:
    admin = db.execute(select(AdminUser).where(AdminUser.email == email)).scalar_one_or_none()
    # Always verify (against a dummy hash if needed) so timing doesn't reveal which emails exist.
    ok = security.verify_password(password, admin.password_hash if admin else None)
    if not ok or admin is None or not admin.is_active:
        reason = "unknown_email" if admin is None else ("inactive" if ok else "bad_password")
        audit.record(db, "admin.login_failed", admin=admin, actor_email=email[:320],
                     details={"reason": reason}, ip=ip)
        raise _invalid_credentials()
    if security.password_needs_rehash(admin.password_hash):
        admin.password_hash = security.hash_password(password)
        db.commit()
    return admin


# ---------- MFA challenge (between password and code) ----------

def _pwc(admin: AdminUser) -> int:
    return int(as_utc(admin.password_changed_at).timestamp()) if admin.password_changed_at else 0


def make_mfa_challenge(admin: AdminUser) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(admin.id), "aud": MFA_AUDIENCE, "iat": now, "exp": now + MFA_CHALLENGE_TTL,
               "pwc": _pwc(admin), "jti": uuid.uuid4().hex}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm=security.JWT_ALG)


def read_mfa_challenge(db: Session, token: str) -> AdminUser:
    expired = HTTPException(status.HTTP_401_UNAUTHORIZED,
                            {"code": "mfa_challenge_expired", "message": "Please sign in again."})
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[security.JWT_ALG], audience=MFA_AUDIENCE,
                             options={"require": ["exp", "sub", "aud", "pwc"]})
        admin = db.get(AdminUser, uuid.UUID(payload["sub"]))
    except (jwt.PyJWTError, ValueError):
        raise expired from None
    if admin is None or not admin.is_active or admin.mfa_enabled_at is None or payload["pwc"] != _pwc(admin):
        raise expired
    return admin


def _secret(admin: AdminUser) -> str | None:
    return crypto.decrypt(admin.mfa_secret_enc) if admin.mfa_secret_enc else None


def check_totp(db: Session, admin: AdminUser, code: str) -> bool:
    """Verify a code against the admin's (pending or active) secret and burn its time step."""
    secret = _secret(admin)
    if not secret:
        return False
    step = totp.verify(secret, code, last_step=admin.mfa_last_step)
    if step is None:
        return False
    admin.mfa_last_step = step
    db.commit()
    return True


def start_mfa_enrolment(db: Session, admin: AdminUser) -> tuple[str, str]:
    if admin.mfa_enabled_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            {"code": "mfa_already_enabled", "message": "Two-step verification is already on."})
    secret = totp.new_secret()
    admin.mfa_secret_enc = crypto.encrypt(secret)
    admin.mfa_last_step = None
    db.commit()
    return secret, totp.provisioning_uri(secret, admin.email, f"{get_settings().app_name} Admin")


# ---------- Sessions ----------

@dataclass
class IssuedSession:
    token: str
    session: AdminSession


def create_session(db: Session, admin: AdminUser, *, mfa_verified: bool, ip: str | None, user_agent: str | None) -> IssuedSession:
    settings = get_settings()
    token = TOKEN_PREFIX + security.new_opaque_token()
    now = utcnow()
    row = AdminSession(
        admin_id=admin.id, token_hash=security.sha256_hex(token), mfa_verified=mfa_verified,
        created_at=now, last_seen_at=now, expires_at=now + timedelta(hours=settings.admin_session_max_hours),
        ip=ip, user_agent=(user_agent or "")[:255] or None,
    )
    db.add(row)
    admin.last_login_at = now
    db.commit()
    return IssuedSession(token=token, session=row)


def idle_deadline(session: AdminSession) -> datetime:
    return as_utc(session.last_seen_at) + timedelta(minutes=get_settings().admin_session_idle_minutes)


def resolve_session(db: Session, token: str) -> tuple[AdminSession, AdminUser] | None:
    if not token.startswith(TOKEN_PREFIX):
        return None
    row = db.execute(
        select(AdminSession).where(AdminSession.token_hash == security.sha256_hex(token))
    ).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        return None
    now = utcnow()
    if as_utc(row.expires_at) <= now or idle_deadline(row) <= now:
        return None
    admin = db.get(AdminUser, row.admin_id)
    if admin is None or not admin.is_active:
        return None
    if admin.password_changed_at is not None and as_utc(row.created_at) < as_utc(admin.password_changed_at):
        return None
    if now - as_utc(row.last_seen_at) >= LAST_SEEN_RESOLUTION:
        row.last_seen_at = now
        db.commit()
    return row, admin


def revoke_session(db: Session, session: AdminSession) -> None:
    if session.revoked_at is None:
        session.revoked_at = utcnow()
        db.commit()


def revoke_all(db: Session, admin: AdminUser, *, except_id: uuid.UUID | None = None) -> None:
    stmt = update(AdminSession).where(AdminSession.admin_id == admin.id, AdminSession.revoked_at.is_(None))
    if except_id is not None:
        stmt = stmt.where(AdminSession.id != except_id)
    db.execute(stmt.values(revoked_at=utcnow()))
    db.commit()


def validate_new_password(password: str, *, email: str) -> None:
    problems = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"Use at least {MIN_PASSWORD_LENGTH} characters.")
    local_part = email.split("@")[0].lower() if email else ""
    if len(local_part) >= 4 and local_part in password.lower():
        problems.append("Don't include your email address in the password.")
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            {"code": "weak_password", "message": " ".join(problems)})
