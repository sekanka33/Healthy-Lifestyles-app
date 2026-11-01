from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import validate_timezone

PASSWORD_MIN, PASSWORD_MAX = 10, 128


def check_password(v: str) -> str:
    if not (PASSWORD_MIN <= len(v) <= PASSWORD_MAX):
        raise ValueError(f"Password must be {PASSWORD_MIN}-{PASSWORD_MAX} characters")
    if len(set(v)) < 4:
        raise ValueError("Password is too simple")
    return v


class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    timezone: str = "UTC"

    _pw = field_validator("password")(check_password)
    _tz = field_validator("timezone")(validate_timezone)

    @field_validator("first_name", "last_name")
    @classmethod
    def strip(cls, v: str | None) -> str | None:
        return v.strip() if v is not None else v


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=PASSWORD_MAX)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=200)


class VerifyEmailIn(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")
    new_password: str

    _pw = field_validator("new_password")(check_password)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=PASSWORD_MAX)
    new_password: str

    _pw = field_validator("new_password")(check_password)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until the access token expires
