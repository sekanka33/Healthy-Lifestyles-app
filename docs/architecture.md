# Architecture

```
Healthy-Lifestyles-app/
├── backend/        Python 3.12+ · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL
├── mobile/         Expo SDK 58 · React Native 0.88 · TypeScript · Expo Router
├── docs/           Design reference, architecture, setup guides
└── picture/        Design reference images (source of truth for visuals)
```

## Key decisions

| Concern | Choice | Why |
|---|---|---|
| Auth | Email + password (Argon2id), short-lived JWT access token + rotating, hashed refresh tokens in DB | Revocable sessions (needed after password reset), no plaintext secrets |
| Subscriptions | **RevenueCat** in front of App Store / Google Play billing | Apple & Google require store billing for in-app digital subscriptions; RevenueCat normalises receipts, renewals, refunds and webhooks for both |
| Entitlement truth | Backend only. Webhooks are authenticated, then the backend re-fetches the subscriber from RevenueCat's REST API before changing entitlement | Client-reported status is never trusted |
| Background jobs | Database-backed job table + `python -m app.worker` | Durable, retryable, idempotent, no extra Redis/Celery infra to start with |
| Email | Provider interface: **Resend** (HTTP API) in prod, SMTP (e.g. Mailpit) in dev | Status tracking: queued → accepted → delivered/bounced (via provider webhook) |
| PDF | ReportLab on the backend; receipts regenerated on demand from immutable payment rows | No large blobs in DB; a receipt can always be reproduced exactly |
| Weather | OpenWeather via backend proxy, coordinates rounded to ~1 km, cached in DB | API key never ships in the app; quota-friendly; less precise location stored |
| Calendar | Google OAuth 2.0 authorisation-code flow run by the backend (state + PKCE). Default scope: `calendar.freebusy`; `calendar.events` requested incrementally only when a Premium user first adds an event | Minimum permissions; refresh tokens encrypted at rest (Fernet) |
| Recommendations | Pure-Python rule engine (`app/services/recommendations`) over free slots + weather + preferences + entitlement | Deterministic, testable, easy to extend with new activity types |
| Offline water logging | Client generates a UUID per entry; server enforces `UNIQUE(user_id, client_id)` | Retries and rapid taps cannot create duplicates; queued entries sync later |
| GPS | `expo-location` + `expo-task-manager` background task; Haversine with accuracy/speed filters | Requires a development build (not Expo Go) |
| Health data | Health Connect (Android) / HealthKit (iOS) via native modules, opt-in per data type, dedup on external record id | Requires development build |

## Day boundaries

All timestamps are stored as UTC `timestamptz`. Each user has an IANA time zone
(`Africa/Johannesburg`, etc.). "Today's total" is computed for the half-open
interval `[local midnight, next local midnight)` converted to UTC, so the
display resets at local midnight without deleting history, and DST days of
23 h / 25 h are handled by `zoneinfo`.

## Plans and enforcement

| Feature | Free | Premium ($11/mo) |
|---|---|---|
| Water tracking, goals, history, reminders, water reports/PDF | ✅ | ✅ |
| Basic current weather | ✅ | ✅ |
| Google Calendar connect + free-slot view + hydration suggestions | ✅ | ✅ |
| Medication schedules, reminders, history | ❌ | ✅ |
| GPS workouts, health integrations, fitness reports | ❌ | ✅ |
| Weather-aware exercise recommendations | ❌ | ✅ |
| Creating calendar events, full recommendations | ❌ | ✅ |

Enforced by a `require_premium` FastAPI dependency that reads the
server-side `subscription_entitlements` row — never a client flag.
