from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core import security
from app.db.base import as_utc
from app.db.session import get_db
from app.models.user import User

DB = Annotated[Session, Depends(get_db)]

_bearer = HTTPBearer(auto_error=False)


def _unauthorized(message: str = "Please sign in.") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, {"code": "not_authenticated", "message": message},
                         headers={"WWW-Authenticate": "Bearer"})


def current_user_any(
    db: DB, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
) -> User:
    """Authenticated user, verified or not (used by verification & profile endpoints)."""
    if creds is None:
        raise _unauthorized()
    decoded = security.decode_access_token(creds.credentials)
    if decoded is None:
        raise _unauthorized("Your session has expired.")
    user_id, issued_at = decoded
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized()
    # Tokens minted before a password change/reset are dead immediately, not after their TTL.
    if user.password_changed_at is not None and issued_at < as_utc(user.password_changed_at).timestamp():
        raise _unauthorized("Your session has expired.")
    return user


def current_user(user: Annotated[User, Depends(current_user_any)]) -> User:
    """Authenticated user with a verified email — required for app features."""
    if user.email_verified_at is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            {"code": "email_not_verified", "message": "Please verify your email first."})
    return user


AnyUser = Annotated[User, Depends(current_user_any)]
VerifiedUser = Annotated[User, Depends(current_user)]


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def require_premium(user: VerifiedUser, db: DB) -> User:
    """Gate for Premium features. Reads only the server-side entitlement (see services/entitlements)."""
    from app.services.entitlements import is_premium

    if not is_premium(db, user):
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED,
                            {"code": "premium_required", "message": "This feature needs Healthy Lifestyles Premium."})
    return user


PremiumUser = Annotated[User, Depends(require_premium)]
