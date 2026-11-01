"""RevenueCat REST client and the rules that turn a subscriber record into our entitlement state.

We never trust what a phone says about a purchase. Entitlements are only written from data fetched
here, server-to-server, with the secret API key (REST API v1: GET /subscribers/{app_user_id}).
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from app.core.config import get_settings


class RevenueCatError(Exception):
    """RevenueCat unreachable or misconfigured. Webhooks answer 503 so RevenueCat retries."""


STORE_MAP = {
    "app_store": "app_store",
    "mac_app_store": "app_store",
    "play_store": "play_store",
    "stripe": "stripe",
    "promotional": "promotional",
}


def normalise_store(store: str | None) -> str | None:
    if not store:
        return None
    s = store.lower()
    return STORE_MAP.get(s, s[:16])


def parse_ts(value: str | int | None) -> datetime | None:
    """RevenueCat uses ISO-8601 strings in REST and epoch milliseconds in webhooks."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class EntitlementState:
    status: str  # active | grace_period | billing_issue | cancelled | expired | refunded
    product_id: str | None
    store: str | None
    expires_at: datetime | None  # for grace_period this is the end of the grace period
    current_period_start: datetime | None
    will_renew: bool
    environment: str  # production | sandbox
    original_transaction_id: str | None


def derive_entitlement(subscriber: dict, entitlement_id: str, now: datetime) -> EntitlementState | None:
    """None means the user has never had this entitlement."""
    ent = (subscriber.get("entitlements") or {}).get(entitlement_id)
    if not ent:
        return None
    product = ent.get("product_identifier")
    sub = (subscriber.get("subscriptions") or {}).get(product) or {}

    expires = parse_ts(ent.get("expires_date"))  # None = lifetime / non-expiring promotional
    grace = parse_ts(ent.get("grace_period_expires_date") or sub.get("grace_period_expires_date"))
    refunded = parse_ts(sub.get("refunded_at"))
    billing_issue = parse_ts(sub.get("billing_issues_detected_at"))
    unsubscribed = parse_ts(sub.get("unsubscribe_detected_at"))

    will_renew = False
    if refunded is not None:
        status = "refunded"
    elif expires is None or expires > now:
        status = "cancelled" if unsubscribed else "active"  # cancelled = paid up, won't renew
        will_renew = unsubscribed is None and expires is not None
    elif grace is not None and grace > now:
        status, expires, will_renew = "grace_period", grace, True
    elif billing_issue is not None:
        status = "billing_issue"
    else:
        status = "expired"

    return EntitlementState(
        status=status,
        product_id=product,
        store=normalise_store(sub.get("store")),
        expires_at=expires,
        current_period_start=parse_ts(ent.get("purchase_date") or sub.get("purchase_date")),
        will_renew=will_renew,
        environment="sandbox" if sub.get("is_sandbox") else "production",
        original_transaction_id=sub.get("original_transaction_id") or sub.get("store_transaction_id"),
    )


class RevenueCatClient:
    def __init__(self, secret_key: str, base_url: str):
        self.secret_key = secret_key
        self.base_url = base_url.rstrip("/")

    def get_subscriber(self, app_user_id: str) -> dict:
        try:
            res = httpx.get(
                f"{self.base_url}/subscribers/{quote(app_user_id, safe='')}",
                headers={"Authorization": f"Bearer {self.secret_key}", "Accept": "application/json"},
                timeout=15,
            )
        except httpx.HTTPError as exc:
            raise RevenueCatError(f"RevenueCat unreachable: {type(exc).__name__}") from exc
        if res.status_code != 200:
            raise RevenueCatError(f"RevenueCat returned HTTP {res.status_code}")
        return res.json().get("subscriber") or {}


def get_client() -> RevenueCatClient:
    s = get_settings()
    if not s.revenuecat_secret_api_key:
        raise RevenueCatError("REVENUECAT_SECRET_API_KEY is not configured")
    return RevenueCatClient(s.revenuecat_secret_api_key, s.revenuecat_api_url)
