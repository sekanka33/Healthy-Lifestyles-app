from fastapi import APIRouter, BackgroundTasks, Request, Response, status

from app.api.deps import DB, AnyUser, client_ip, user_agent
from app.api.v1.me import user_out
from app.core import rate_limit
from app.schemas.auth import (
    ChangePasswordIn,
    ForgotPasswordIn,
    LoginIn,
    RefreshIn,
    RegisterIn,
    ResetPasswordIn,
    TokenPair,
    VerifyEmailIn,
)
from app.schemas.user import UserOut
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

MIN15 = 15 * 60
HOUR = 60 * 60


class SessionOut(TokenPair):
    user: UserOut


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=SessionOut)
def register(data: RegisterIn, request: Request, background: BackgroundTasks, db: DB):
    rate_limit.hit(db, f"register:ip:{client_ip(request)}", limit=10, window_seconds=HOUR)
    user, tokens = auth_service.register(db, background, data, user_agent(request))
    return SessionOut(**tokens.model_dump(), user=user_out(db, user))


@router.post("/login", response_model=SessionOut)
def login(data: LoginIn, request: Request, db: DB):
    email = auth_service.normalise_email(data.email)
    rate_limit.hit(db, f"login:ip:{client_ip(request)}", limit=30, window_seconds=MIN15)
    rate_limit.hit(db, f"login:email:{email}", limit=10, window_seconds=MIN15)
    user = auth_service.authenticate(db, email, data.password)
    rate_limit.reset(db, f"login:email:{email}")
    tokens = auth_service.issue_tokens(db, user, user_agent=user_agent(request))
    return SessionOut(**tokens.model_dump(), user=user_out(db, user))


@router.post("/refresh", response_model=TokenPair)
def refresh(data: RefreshIn, request: Request, db: DB):
    rate_limit.hit(db, f"refresh:ip:{client_ip(request)}", limit=60, window_seconds=MIN15)
    return auth_service.rotate_refresh_token(db, data.refresh_token, user_agent(request))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(data: RefreshIn, db: DB):
    auth_service.logout(db, data.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/verify-email", response_model=UserOut)
def verify_email(data: VerifyEmailIn, user: AnyUser, db: DB):
    rate_limit.hit(db, f"verify:user:{user.id}", limit=10, window_seconds=MIN15)
    return user_out(db, auth_service.verify_email(db, user, data.code))


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
def resend_verification(user: AnyUser, background: BackgroundTasks, db: DB):
    rate_limit.hit(db, f"resend:user:{user.id}", limit=5, window_seconds=HOUR)
    auth_service.send_verification_code(db, background, user, enforce_cooldown=True)
    return {"status": "sent"}


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(data: ForgotPasswordIn, request: Request, background: BackgroundTasks, db: DB):
    email = auth_service.normalise_email(data.email)
    rate_limit.hit(db, f"forgot:ip:{client_ip(request)}", limit=10, window_seconds=HOUR)
    rate_limit.hit(db, f"forgot:email:{email}", limit=3, window_seconds=HOUR)
    auth_service.request_password_reset(db, background, email)
    return {"status": "If an account exists for that email, we've sent a reset code."}


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(data: ResetPasswordIn, request: Request, db: DB):
    email = auth_service.normalise_email(data.email)
    rate_limit.hit(db, f"reset:ip:{client_ip(request)}", limit=20, window_seconds=HOUR)
    rate_limit.hit(db, f"reset:email:{email}", limit=10, window_seconds=HOUR)
    auth_service.reset_password(db, email, data.code, data.new_password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/change-password", response_model=TokenPair)
def change_password(data: ChangePasswordIn, request: Request, user: AnyUser, db: DB):
    rate_limit.hit(db, f"change-pw:user:{user.id}", limit=10, window_seconds=HOUR)
    return auth_service.change_password(db, user, data.current_password, data.new_password, user_agent(request))
