"""Password hashing, JWT access tokens and opaque secret helpers.

- Passwords: Argon2id (argon2-cffi defaults follow RFC 9106 low-memory profile).
- Access tokens: short-lived HS256 JWTs carrying only the user id.
- Refresh tokens / reset tokens / verification codes: random secrets, only a hash is stored.
"""

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

_hasher = PasswordHasher()
# Verifying against this when the account doesn't exist keeps login timing uniform.
_DUMMY_HASH = _hasher.hash("timing-equaliser-not-a-real-password")

JWT_ALG = "HS256"
JWT_AUDIENCE = "lifepulse-app"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def create_access_token(user_id: uuid.UUID) -> tuple[str, int]:
    settings = get_settings()
    ttl = settings.access_token_ttl_minutes * 60
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "aud": JWT_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(seconds=ttl),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALG), ttl


def decode_access_token(token: str) -> tuple[uuid.UUID, int] | None:
    """Returns (user_id, issued_at_epoch_seconds) for a valid access token, else None."""
    try:
        payload = jwt.decode(
            token, get_settings().jwt_secret, algorithms=[JWT_ALG], audience=JWT_AUDIENCE,
            options={"require": ["exp", "iat", "sub", "aud"]},
        )
        if payload.get("type") != "access":
            return None
        return uuid.UUID(payload["sub"]), int(payload["iat"])
    except (jwt.PyJWTError, ValueError):
        return None


def new_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_numeric_code(digits: int = 6) -> str:
    return f"{secrets.randbelow(10**digits):0{digits}d}"


def hash_code(code: str, *, scope: str) -> str:
    """Keyed hash for short codes: a stolen DB alone can't brute-force 6-digit codes offline."""
    key = get_settings().jwt_secret.encode()
    return hmac.new(key, f"{scope}:{code}".encode(), hashlib.sha256).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
