# LifePulse — Wellness & Fitness App

Hydration tracking (Free) plus medication reminders, GPS workouts, weather-aware
recommendations and Google Calendar planning (Premium, $11 USD / month).

- `mobile/` — Expo SDK 58 · React Native · TypeScript · Expo Router
- `backend/` — FastAPI · SQLAlchemy · Alembic · PostgreSQL
- `docs/` — [design reference](docs/design-reference.md), [architecture](docs/architecture.md), [subscriptions setup](docs/subscriptions-setup.md), [calendar setup](docs/calendar-setup.md), [deployment](docs/deployment.md), [privacy policy template](docs/privacy-policy-template.md)

## Status

| Phase | Status |
|---|---|
| 1. Inspection & design analysis | ✅ Done |
| 2. Architecture, schema, dev environment | ✅ Done (4 tests passing) |
| 3. Auth, profile, hydration | ✅ Done (30 backend tests passing) |
| 4. Animated glass | ✅ Done (7 mobile unit tests passing) |
| 5. Subscriptions | ✅ Done (45 backend tests passing) — see [setup](docs/subscriptions-setup.md) |
| 6. Medication | ✅ Done (70 backend tests passing) |
| 7. GPS fitness & health | ✅ GPS workouts, goals, health import API (84 backend tests) — device health-app sync pending |
| 8. Weather | ✅ Done (93 backend tests passing) |
| 9. Calendar & recommendations | ✅ Done (112 backend tests) — see [setup](docs/calendar-setup.md) |
| 10. Reports, email, privacy, deployment | ✅ Done (129 backend tests) — see [deployment](docs/deployment.md) |

## Prerequisites

- Python 3.12+ (developed on 3.15)
- Node 20+ (developed on 26)
- PostgreSQL 16+ (not required for the automated test suite, which uses SQLite)

## Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows   (source .venv/bin/activate on macOS/Linux)
pip install -e ".[dev]"
copy .env.example .env            # then fill in values
alembic upgrade head              # requires DATABASE_URL to point at PostgreSQL
uvicorn app.main:app --reload     # API docs at http://localhost:8000/docs
python -m app.worker              # background jobs: report/receipt/export emails (2nd terminal)
pytest                            # tests
```

With `EMAIL_PROVIDER=disabled` in development, verification and reset codes are printed
to the API log instead of being emailed — handy before a mail server is set up. For real
emails locally, run [Mailpit](https://mailpit.axllent.org/) and set `EMAIL_PROVIDER=smtp`.

No PostgreSQL yet? For a quick local try-out, `DATABASE_URL=sqlite:///./dev.db` works too.

**Test accounts:** `python -m app.scripts.seed_demo_accounts` creates (or resets) a verified Free
account `free.demo@example.com` and a Premium one `premium.demo@example.com` (promotional
entitlement, no expiry) and prints fresh passwords. It refuses to run with `ENVIRONMENT=production`.

To run the migration test against PostgreSQL too, set `TEST_POSTGRES_URL` to an
**empty, disposable** database.

## Mobile

```bash
cd mobile
npm install
copy .env.example .env.local      # set EXPO_PUBLIC_API_URL if the defaults below don't fit
npx expo start
npm test                          # glass maths unit tests (Node's built-in runner)
npm run typecheck
```

In development the app talks to port 8000 on the computer running `expo start` (it reads the
address from Expo), so a phone on the same Wi-Fi works without setup — start the API with
`uvicorn app.main:app --reload --host 0.0.0.0`. Set `EXPO_PUBLIC_API_URL` to override.

**"Can't reach the server" on a phone (Windows):** Windows Firewall blocks incoming connections on
networks marked *Public*. In an **administrator** PowerShell, mark your home Wi-Fi as private and
allow the API port on private networks only:

```powershell
Set-NetConnectionProfile -InterfaceAlias "Wi-Fi" -NetworkCategory Private
New-NetFirewallRule -DisplayName "LifePulse API (dev)" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
```

GPS background tracking, Health Connect, HealthKit and in-app purchases need a
**development build** (`npx expo run:android` / `eas build --profile development`);
Expo Go can't run them.
