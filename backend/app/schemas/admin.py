import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.auth import PASSWORD_MAX

TotpCode = Field(pattern=r"^\s*\d{3}\s?\d{3}\s*$")


class AdminLoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=PASSWORD_MAX)


class AdminMfaVerifyIn(BaseModel):
    mfa_token: str = Field(min_length=20, max_length=2000)
    code: str = TotpCode


class AdminCodeIn(BaseModel):
    code: str = TotpCode


class AdminMfaDisableIn(BaseModel):
    password: str = Field(min_length=1, max_length=PASSWORD_MAX)
    code: str = TotpCode


class AdminChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=PASSWORD_MAX)
    new_password: str = Field(min_length=1, max_length=PASSWORD_MAX)


class AdminMe(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    role_label: str
    permissions: list[str]
    mfa_enabled: bool
    mfa_required: bool
    # True when MFA is required but this session hasn't proven it: only MFA enrolment is allowed.
    mfa_setup_needed: bool
    last_login_at: datetime | None


class AdminSessionOut(BaseModel):
    status: Literal["ok"] = "ok"
    token: str
    expires_at: datetime
    idle_timeout_minutes: int
    admin: AdminMe


class AdminMfaChallengeOut(BaseModel):
    status: Literal["mfa_required"] = "mfa_required"
    mfa_token: str


class AdminMfaSetupOut(BaseModel):
    secret: str
    otpauth_uri: str
