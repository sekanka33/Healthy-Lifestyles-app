"""Account lifecycle: registration, email verification, sessions (refresh-token rotation),
password reset and change. Routers stay thin; all rules live here."""

import uuid
from datetime import timedelta

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.db.base import as_utc, utcnow
from app.models.user import (
    EmailPreferences,
    NotificationPreferences,
    OneTimeCode,
    RefreshToken,
    User,
    UserPreferences,
)
from app.schemas.auth import RegisterIn, TokenPair
from app.services import email as email_service

VERIFY, RESET = "email_verification", "password_reset"


def http_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code, {"code": code, "message": message})


def normalise_email(email: str) -> str:
    return email.strip().lower()


# ---------------------------------------------------------------- sessions

def issue_tokens(db: Session, user: User, *, family_id: uuid.UUID | None = None,
                 user_agent: str | None = None) -> TokenPair:
    settings = get_settings()
    raw = security.new_opaque_token()
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=security.sha256_hex(raw),
        family_id=family_id or uuid.uuid4(),
        expires_at=utcnow() + timedelta(days=settings.refresh_token_ttl_days),
        user_agent=(user_agent or "")[:255] or None,
    ))
    db.commit()
    access, ttl = security.create_access_token(user.id)
    return TokenPair(access_token=access, refresh_token=raw, expires_in=ttl)


def rotate_refresh_token(db: Session, raw: str, user_agent: str | None) -> TokenPair:
    invalid = http_error(status.HTTP_401_UNAUTHORIZED, "invalid_refresh_token", "Please sign in again.")
    token = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == security.sha256_hex(raw)).with_for_update()
    ).scalar_one_or_none()
    if token is None:
        raise invalid
    if token.revoked_at is not None:
        # A rotated token was replayed: assume theft and end every session in that family.
        revoke_family(db, token.family_id)
        raise invalid
    if as_utc(token.expires_at) <= utcnow():
        raise invalid
    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise invalid
    token.revoked_at = utcnow()
    return issue_tokens(db, user, family_id=token.family_id, user_agent=user_agent)


def revoke_family(db: Session, family_id: uuid.UUID) -> None:
    db.execute(update(RefreshToken).where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
               .values(revoked_at=utcnow()))
    db.commit()


def revoke_all_sessions(db: Session, user_id: uuid.UUID) -> None:
    db.execute(update(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
               .values(revoked_at=utcnow()))
    db.commit()


def logout(db: Session, raw: str) -> None:
    token = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == security.sha256_hex(raw))
    ).scalar_one_or_none()
    if token is not None:
        revoke_family(db, token.family_id)


# ---------------------------------------------------------------- registration & login

def register(db: Session, background: BackgroundTasks, data: RegisterIn, user_agent: str | None) -> tuple[User, TokenPair]:
    from app.services.hydration import set_goal  # avoid import cycle

    email = normalise_email(data.email)
    if db.execute(select(User.id).where(User.email == email)).first():
        raise http_error(status.HTTP_409_CONFLICT, "email_taken", "An account with this email already exists.")
    user = User(id=uuid.uuid4(), email=email, password_hash=security.hash_password(data.password), first_name=data.first_name,
                last_name=data.last_name or None, timezone=data.timezone)
    db.add(user)
    try:
        db.flush()
    except IntegrityError:  # lost a race with a simultaneous sign-up for the same email
        db.rollback()
        raise http_error(status.HTTP_409_CONFLICT, "email_taken", "An account with this email already exists.") from None
    db.add_all([UserPreferences(user_id=user.id), NotificationPreferences(user_id=user.id),
                EmailPreferences(user_id=user.id)])
    set_goal(db, user, 2000, commit=False)
    db.commit()
    send_verification_code(db, background, user)
    return user, issue_tokens(db, user, user_agent=user_agent)


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.execute(select(User).where(User.email == normalise_email(email))).scalar_one_or_none()
    ok = security.verify_password(password, user.password_hash if user else None)
    if not ok or user is None or not user.is_active:
        raise http_error(status.HTTP_401_UNAUTHORIZED, "invalid_credentials", "Email or password is incorrect.")
    if security.password_needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(password)
        db.commit()
    return user


# ---------------------------------------------------------------- one-time codes

def _latest_code(db: Session, user_id: uuid.UUID, purpose: str) -> OneTimeCode | None:
    return db.execute(
        select(OneTimeCode)
        .where(OneTimeCode.user_id == user_id, OneTimeCode.purpose == purpose, OneTimeCode.consumed_at.is_(None))
        .order_by(OneTimeCode.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _new_code(db: Session, user: User, purpose: str, ttl_minutes: int) -> tuple[OneTimeCode, str]:
    # Only one live code per purpose: issuing a new one invalidates the old.
    db.execute(update(OneTimeCode)
               .where(OneTimeCode.user_id == user.id, OneTimeCode.purpose == purpose, OneTimeCode.consumed_at.is_(None))
               .values(consumed_at=utcnow()))
    code = security.new_numeric_code()
    row = OneTimeCode(user_id=user.id, purpose=purpose, code_hash=security.hash_code(code, scope=purpose),
                      expires_at=utcnow() + timedelta(minutes=ttl_minutes))
    db.add(row)
    db.commit()
    return row, code


def _check_code(db: Session, user: User | None, purpose: str, code: str) -> bool:
    """Consumes the code on success. Wrong guesses count towards the attempt limit."""
    if user is None:
        return False
    row = _latest_code(db, user.id, purpose)
    if row is None or as_utc(row.expires_at) <= utcnow():
        return False
    if row.attempts >= get_settings().verification_max_attempts:
        return False
    if not security.constant_time_equals(row.code_hash, security.hash_code(code, scope=purpose)):
        row.attempts += 1
        db.commit()
        return False
    row.consumed_at = utcnow()
    return True


def send_verification_code(db: Session, background: BackgroundTasks, user: User, *, enforce_cooldown: bool = False) -> None:
    settings = get_settings()
    if user.email_verified_at is not None:
        raise http_error(status.HTTP_409_CONFLICT, "already_verified", "Your email is already verified.")
    if enforce_cooldown:
        last = db.execute(
            select(OneTimeCode.created_at).where(OneTimeCode.user_id == user.id, OneTimeCode.purpose == VERIFY)
            .order_by(OneTimeCode.created_at.desc()).limit(1)
        ).scalar_one_or_none()
        if last is not None:
            wait = settings.verification_resend_cooldown_seconds - (utcnow() - as_utc(last)).total_seconds()
            if wait > 0:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                    {"code": "resend_cooldown", "message": "Please wait before requesting another code."},
                                    headers={"Retry-After": str(int(wait) + 1)})
    row, code = _new_code(db, user, VERIFY, settings.verification_code_ttl_minutes)
    email_service.queue_email(
        db, background, to=user.email, user_id=user.id, template="email_verification",
        subject=f"{code} is your {settings.app_name} verification code",
        text=(f"Hi {user.first_name},\n\nYour verification code is {code}.\n"
              f"It expires in {settings.verification_code_ttl_minutes} minutes.\n\n"
              "If you didn't create an account, you can ignore this email."),
        idempotency_key=f"otc:{row.id}",
    )


def verify_email(db: Session, user: User, code: str) -> User:
    if user.email_verified_at is not None:
        return user
    if not _check_code(db, user, VERIFY, code):
        raise http_error(status.HTTP_400_BAD_REQUEST, "invalid_code", "That code is invalid or has expired.")
    user.email_verified_at = utcnow()
    db.commit()
    return user


def request_password_reset(db: Session, background: BackgroundTasks, email: str) -> None:
    """Always succeeds from the caller's view, so it can't be used to discover accounts."""
    settings = get_settings()
    user = db.execute(select(User).where(User.email == normalise_email(email))).scalar_one_or_none()
    if user is None or not user.is_active:
        return
    row, code = _new_code(db, user, RESET, settings.password_reset_ttl_minutes)
    email_service.queue_email(
        db, background, to=user.email, user_id=user.id, template="password_reset",
        subject=f"Reset your {settings.app_name} password",
        text=(f"Hi {user.first_name},\n\nUse this code to reset your password: {code}\n"
              f"It expires in {settings.password_reset_ttl_minutes} minutes.\n\n"
              "If you didn't ask for this, ignore this email — your password won't change."),
        idempotency_key=f"otc:{row.id}",
    )


def reset_password(db: Session, email: str, code: str, new_password: str) -> None:
    user = db.execute(select(User).where(User.email == normalise_email(email))).scalar_one_or_none()
    if user is None or not _check_code(db, user, RESET, code):
        raise http_error(status.HTTP_400_BAD_REQUEST, "invalid_code", "That code is invalid or has expired.")
    _set_password(db, user, new_password)
    # Receiving the code proves control of the inbox.
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
    db.commit()
    revoke_all_sessions(db, user.id)


def change_password(db: Session, user: User, current: str, new: str, user_agent: str | None) -> TokenPair:
    if not security.verify_password(current, user.password_hash):
        raise http_error(status.HTTP_400_BAD_REQUEST, "invalid_password", "Current password is incorrect.")
    _set_password(db, user, new)
    db.commit()
    revoke_all_sessions(db, user.id)
    return issue_tokens(db, user, user_agent=user_agent)


def _set_password(db: Session, user: User, new_password: str) -> None:
    user.password_hash = security.hash_password(new_password)
    # Whole seconds: JWT `iat` has second precision, and tokens minted before this are rejected.
    user.password_changed_at = utcnow().replace(microsecond=0)
