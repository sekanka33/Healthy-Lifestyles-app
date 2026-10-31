"""Application settings, loaded from environment variables (see .env.example).

Secrets are never hard-coded. Defaults are only safe development values; in
production, `validate_production()` refuses to start with insecure settings.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    app_name: str = "Healthy Lifestyles"
    # Trusted public URLs — links in emails are built ONLY from these, never from request headers.
    public_api_url: str = "http://localhost:8000"
    app_deep_link_base: str = "healthylifestyles://"
    support_email: str = "support@example.com"

    database_url: str = "postgresql+psycopg://wellness:wellness@localhost:5432/wellness"

    # Auth
    jwt_secret: str = Field(default="dev-insecure-change-me", min_length=16)
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    verification_code_ttl_minutes: int = 10
    verification_resend_cooldown_seconds: int = 60
    verification_max_attempts: int = 5
    password_reset_ttl_minutes: int = 30

    # Encryption key for OAuth tokens at rest (Fernet, urlsafe base64, 32 bytes).
    token_encryption_key: str | None = None

    # Email
    email_provider: Literal["smtp", "resend", "disabled"] = "disabled"
    email_from: str = "Healthy Lifestyles <no-reply@example.com>"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = False
    resend_api_key: str | None = None

    # Integrations
    openweather_api_key: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8000/api/v1/calendar/oauth/callback"
    revenuecat_secret_api_key: str | None = None
    revenuecat_webhook_auth: str | None = None
    revenuecat_premium_entitlement: str = "premium"

    def validate_production(self) -> None:
        if self.environment != "production":
            return
        problems = []
        if self.jwt_secret.startswith("dev-") or len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET must be a random value of at least 32 characters")
        if not self.token_encryption_key:
            problems.append("TOKEN_ENCRYPTION_KEY is required")
        if not self.public_api_url.startswith("https://"):
            problems.append("PUBLIC_API_URL must use https")
        if self.email_provider == "disabled":
            problems.append("EMAIL_PROVIDER must be configured")
        if problems:
            raise RuntimeError("Insecure production configuration: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()
