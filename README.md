# Healthy Lifestyles — Wellness & Fitness App

Hydration tracking (Free) plus medication reminders, GPS workouts, weather-aware
recommendations and Google Calendar planning (Premium, $11 USD / month).

- `mobile/` — Expo SDK 58 · React Native · TypeScript · Expo Router
- `backend/` — FastAPI · SQLAlchemy · Alembic · PostgreSQL
- `docs/` — [design reference](docs/design-reference.md), [architecture](docs/architecture.md), [subscriptions setup](docs/subscriptions-setup.md), [calendar setup](docs/calendar-setup.md)

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
| 10. Reports, email, privacy, deployment | ⏳ Next |

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

The app calls `http://10.0.2.2:8000` on the Android emulator and `http://localhost:8000`
on iOS simulator / web. On a physical phone set `EXPO_PUBLIC_API_URL` to your computer's
LAN address and start the API with `uvicorn app.main:app --host 0.0.0.0`.

GPS background tracking, Health Connect, HealthKit and in-app purchases need a
**development build** (`npx expo run:android` / `eas build --profile development`);
Expo Go can't run them.
