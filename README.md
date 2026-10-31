# Healthy Lifestyles — Wellness & Fitness App

Hydration tracking (Free) plus medication reminders, GPS workouts, weather-aware
recommendations and Google Calendar planning (Premium, $11 USD / month).

- `mobile/` — Expo SDK 58 · React Native · TypeScript · Expo Router
- `backend/` — FastAPI · SQLAlchemy · Alembic · PostgreSQL
- `docs/` — [design reference](docs/design-reference.md), [architecture](docs/architecture.md)

## Status

| Phase | Status |
|---|---|
| 1. Inspection & design analysis | ✅ Done |
| 2. Architecture, schema, dev environment | ✅ Done (4 tests passing) |
| 3. Auth, profile, hydration | ⏳ Next |
| 4. Animated glass | — |
| 5. Subscriptions | — |
| 6. Medication | — |
| 7. GPS fitness & health | — |
| 8. Weather | — |
| 9. Calendar & recommendations | — |
| 10. Reports, email, privacy, deployment | — |

## Prerequisites

- Python 3.12+ (developed on 3.15)
- Node 20+ (developed on 26)
- PostgreSQL 16+ (not required for the automated test suite, which uses SQLite)

## Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows   (source .venv/bin/activate on macOS/Linux)
pip install fastapi uvicorn "pydantic[email]" pydantic-settings sqlalchemy alembic "psycopg[binary]" argon2-cffi pyjwt httpx cryptography reportlab pytest
copy .env.example .env            # then fill in values
alembic upgrade head              # requires DATABASE_URL to point at PostgreSQL
uvicorn app.main:app --reload     # API docs at http://localhost:8000/docs
pytest                            # tests
```

To run the migration test against PostgreSQL too, set `TEST_POSTGRES_URL` to an
**empty, disposable** database.

## Mobile

```bash
cd mobile
npm install
npx expo start
```

GPS background tracking, Health Connect, HealthKit and in-app purchases need a
**development build** (`npx expo run:android` / `eas build --profile development`);
Expo Go can't run them.
