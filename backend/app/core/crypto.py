"""Symmetric encryption for secrets at rest (OAuth tokens, PKCE verifiers). Fernet = AES-128-CBC + HMAC."""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class EncryptionNotConfigured(Exception):
    pass


def _fernet() -> Fernet:
    key = get_settings().token_encryption_key
    if not key:
        raise EncryptionNotConfigured("TOKEN_ENCRYPTION_KEY is not set")
    return Fernet(key.encode())


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str | None:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return None  # key rotated or data tampered with: treat as missing
