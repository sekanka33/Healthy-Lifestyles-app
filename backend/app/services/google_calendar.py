"""Thin Google OAuth 2.0 + Calendar API client (server-side authorisation-code flow with PKCE).

Scopes: `calendar.freebusy` by default (only busy/free times — never event titles or details).
`calendar.events` is requested incrementally, only when a Premium user first adds a suggestion to
their calendar.
"""

import base64
import hashlib
import secrets
from datetime import datetime
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://www.googleapis.com/calendar/v3"
SCOPE_FREEBUSY = "https://www.googleapis.com/auth/calendar.freebusy"
SCOPE_EVENTS = "https://www.googleapis.com/auth/calendar.events"


class GoogleError(Exception):
    """Google unreachable or rejected the request. `auth_revoked` = the user withdrew access."""

    def __init__(self, message: str, *, auth_revoked: bool = False):
        super().__init__(message)
        self.auth_revoked = auth_revoked


class GoogleNotConfigured(Exception):
    pass


def new_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


class GoogleClient:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id, self.client_secret, self.redirect_uri = client_id, client_secret, redirect_uri

    def authorization_url(self, *, state: str, code_challenge: str, scopes: list[str]) -> str:
        return AUTH_URL + "?" + urlencode({
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        })

    def _post_token(self, data: dict) -> dict:
        try:
            res = httpx.post(TOKEN_URL, data={**data, "client_id": self.client_id, "client_secret": self.client_secret},
                             timeout=15)
        except httpx.HTTPError as exc:
            raise GoogleError(type(exc).__name__) from exc
        if res.status_code != 200:
            body = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
            raise GoogleError(f"token endpoint {res.status_code}", auth_revoked=body.get("error") == "invalid_grant")
        return res.json()

    def exchange_code(self, code: str, verifier: str) -> dict:
        return self._post_token({"code": code, "code_verifier": verifier, "grant_type": "authorization_code",
                                 "redirect_uri": self.redirect_uri})

    def refresh(self, refresh_token: str) -> dict:
        return self._post_token({"refresh_token": refresh_token, "grant_type": "refresh_token"})

    def revoke(self, token: str) -> None:
        try:
            httpx.post(REVOKE_URL, data={"token": token}, timeout=10)
        except httpx.HTTPError:
            pass  # best effort: the local copy is deleted regardless

    def _call(self, method: str, path: str, access_token: str, **kw) -> dict:
        try:
            res = httpx.request(method, f"{API}{path}", headers={"Authorization": f"Bearer {access_token}"}, timeout=15, **kw)
        except httpx.HTTPError as exc:
            raise GoogleError(type(exc).__name__) from exc
        if res.status_code == 401:
            raise GoogleError("unauthorised", auth_revoked=True)
        if res.status_code >= 400:
            raise GoogleError(f"calendar API {res.status_code}")
        return res.json()

    def free_busy(self, access_token: str, start: datetime, end: datetime, calendar_ids: list[str]) -> list[tuple[str, str]]:
        body = {"timeMin": start.isoformat(), "timeMax": end.isoformat(), "items": [{"id": c} for c in calendar_ids]}
        data = self._call("POST", "/freeBusy", access_token, json=body)
        busy = []
        for cal in (data.get("calendars") or {}).values():
            busy.extend((b["start"], b["end"]) for b in cal.get("busy", []))
        return busy

    def create_event(self, access_token: str, *, calendar_id: str, summary: str, description: str,
                     start: datetime, end: datetime, tz: str) -> dict:
        body = {
            "summary": summary, "description": description,
            "start": {"dateTime": start.isoformat(), "timeZone": tz},
            "end": {"dateTime": end.isoformat(), "timeZone": tz},
            "reminders": {"useDefault": True},
            "source": {"title": get_settings().app_name, "url": get_settings().public_api_url},
        }
        return self._call("POST", f"/calendars/{calendar_id}/events", access_token, json=body)


def get_client() -> GoogleClient:
    s = get_settings()
    if not s.google_client_id or not s.google_client_secret:
        raise GoogleNotConfigured("GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are not set")
    return GoogleClient(s.google_client_id, s.google_client_secret, s.google_redirect_uri)
