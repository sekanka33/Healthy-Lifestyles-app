# Google Calendar setup

The backend runs Google's OAuth 2.0 authorisation-code flow (with PKCE) on the server. The app only
opens Google's consent page in a secure browser session; Google tokens never reach the phone.

## 1. Google Cloud project
1. console.cloud.google.com → create a project → **APIs & Services → Library** → enable
   **Google Calendar API**.
2. **OAuth consent screen**: External, app name "LifePulse", support email, privacy policy
   URL. Add the scopes below. While in "Testing", add your Google account as a test user.
3. **Credentials → Create credentials → OAuth client ID → Web application**.
   Authorised redirect URI: `https://<your api>/api/v1/calendar/oauth/callback`
   (local: `http://localhost:8000/api/v1/calendar/oauth/callback`).
4. Put the client ID / secret in `backend/.env` (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
   `GOOGLE_REDIRECT_URI`) and set `TOKEN_ENCRYPTION_KEY`
   (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`).

## Scopes (least privilege)
| Scope | When | Why |
|---|---|---|
| `calendar.freebusy` | first connect (any plan) | Busy/free times only — never titles, guests or details |
| `calendar.events` | asked the first time a Premium user taps "Add to calendar" | Create the event they approved |

Google classes `calendar.events` as a *sensitive* scope: before launch, submit the app for OAuth
verification (Google reviews the privacy policy and a short demo video). `calendar.freebusy` alone
needs less review.

## Testing on a phone
The redirect returns to the app via `lifepulse://calendar-connected`, which needs a
development or store build (the scheme is set in `app.json`). On a physical phone the backend must be
reachable at `GOOGLE_REDIRECT_URI` — for local testing use a tunnel (e.g. `cloudflared` or `ngrok`)
and register that HTTPS URL as the redirect URI.
