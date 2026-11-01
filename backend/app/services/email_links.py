"""Signed one-click unsubscribe links (RFC 8058). Links are built only from the trusted
PUBLIC_API_URL setting — never from request headers — so they can't be pointed elsewhere."""

import hashlib
import hmac
import uuid
from urllib.parse import urlencode

from app.core.config import get_settings

# Email category → EmailPreferences field and its "off" value.
CATEGORIES = {
    "water": ("water_summary", "off"),
    "fitness": ("fitness_report", "off"),
    "medication": ("medication_report", "off"),
    "combined": ("combined_weekly_report", False),
    "product": ("product_updates", False),
}


def _sig(user_id: uuid.UUID, category: str) -> str:
    key = get_settings().jwt_secret.encode()
    return hmac.new(key, f"unsubscribe:{user_id}:{category}".encode(), hashlib.sha256).hexdigest()[:32]


def unsubscribe_url(user_id: uuid.UUID, category: str) -> str:
    q = urlencode({"u": str(user_id), "c": category, "t": _sig(user_id, category)})
    return f"{get_settings().public_api_url.rstrip('/')}/api/v1/email/unsubscribe?{q}"


def verify(user_id: str, category: str, token: str) -> uuid.UUID | None:
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return None
    if category not in CATEGORIES or not hmac.compare_digest(_sig(uid, category), token or ""):
        return None
    return uid


def list_unsubscribe_headers(user_id: uuid.UUID, category: str) -> dict:
    return {"List-Unsubscribe": f"<{unsubscribe_url(user_id, category)}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
