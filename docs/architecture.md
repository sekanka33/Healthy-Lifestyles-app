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

## API (Phase 3)

All routes are under `/api/v1`. Errors always look like `{"error": {"code", "message", "details"?}}`.
Interactive docs: `http://localhost:8000/docs` (disabled in production).

| Method & path | Auth | Purpose |
|---|---|---|
| `POST /auth/register` | — | Create account, returns tokens + user, emails a 6-digit code |
| `POST /auth/verify-email` | any user | Confirm the code (5 attempts, 10 min TTL) |
| `POST /auth/resend-verification` | any user | New code (60 s cooldown); old code stops working |
| `POST /auth/login` | — | Email + password → tokens + user |
| `POST /auth/refresh` | — | Rotate refresh token; replaying an old one revokes the whole session family |
| `POST /auth/logout` | — | Revoke the refresh token's session |
| `POST /auth/forgot-password` | — | Always 202 (no account enumeration); emails a 6-digit code |
| `POST /auth/reset-password` | — | Code + new password; signs out every session |
| `POST /auth/change-password` | any user | Signs out other sessions, returns fresh tokens |
| `GET/PATCH /me` | any user | Profile (name, time zone, units, locale). Email/plan are read-only |
| `GET/PATCH /me/notification-preferences` | any user | Reminder settings |
| `POST /hydration/entries` | verified | Log water; 201 new, 200 idempotent replay of the same `client_id` |
| `DELETE /hydration/entries/{client_id}` | verified | Undo (soft delete, idempotent) |
| `GET /hydration/today` · `GET /hydration/days/{date}` | verified | Total, goal, progress and entries for a local day |
| `GET /hydration/history?from&to` | verified | Per-day totals (default last 7 days, max 366) |
| `GET/PUT /hydration/goal` | verified | Daily goal; changes apply from today without rewriting past days |

**Auth details.** Access tokens are 15-minute HS256 JWTs; tokens issued before a password
change are rejected at once. Refresh tokens are opaque, stored as SHA-256 hashes, rotate on every
use, and live in the device keychain/keystore (`expo-secure-store`). One-time codes are stored as
keyed HMACs. Login, registration, reset and verification are rate limited (DB-backed buckets).
The mobile client refreshes single-flight, because two parallel refreshes would look like token theft.

**Offline hydration.** The app writes each tap to a persisted queue (AsyncStorage) with a device
UUID before calling the API, shows `server snapshot + queued adds − queued deletes`, and flushes the
queue in order on launch, focus, foreground and after each tap. Undo of an unsynced tap just
removes it from the queue.

## API (Phase 5 — subscriptions)

| Method & path | Auth | Purpose |
|---|---|---|
| `GET /billing/status` | any user | Plan + entitlement (status, expiry, renews?, store, sandbox?) |
| `POST /billing/sync` | any user | After purchase/restore: server re-fetches from RevenueCat. Request body is ignored |
| `GET /billing/transactions` | any user | Payment ledger (amount/currency exactly as the store reported) |
| `GET /billing/transactions/{id}/receipt.pdf` | owner only | Receipt rendered on demand (ReportLab) |
| `POST /billing/webhooks/revenuecat` | shared secret | Idempotent on event id; 503 on RevenueCat outage so it retries |

Premium-only routes depend on `PremiumUser` (`require_premium`), which answers **402
`premium_required`** unless the server-side entitlement is active, cancelled-but-paid or in grace
period, and not past `expires_at`. See [subscriptions setup](subscriptions-setup.md).

## Guest mode

**The first screen is always the app's content.** Everyone opens straight into the tabs (Water,
History, Meds, Profile) and can browse freely — visitors without an account and accounts whose email
isn't verified yet alike:
Water and History show clearly labelled **sample** data, Profile shows a guest overview with the
Free vs Premium feature table and the settings that an account unlocks. The tab bar works normally.
Every other button or control (water chips, + WATER, undo, custom amount, history range, profile
rows) goes through `useAccountGate()` and opens the Login/Register screen. That screen has **no exit
back to browsing**: there's no "continue as guest" button, the iOS swipe-to-dismiss gesture is off and
Android's back button is swallowed, so the only way forward is to sign in or create an account.
Navigation between sign-in, registration and password reset works normally. Guests never call account APIs. Account-only screens
(`premium`, `payments`, `change-password`) are guarded by `Stack.Protected`. After sign-in the modal
closes onto the same tab with real data. Straight after registering, the verify-email screen opens
(same no-way-back rule). An unverified account that reopens the app later lands on the content again,
and any action outside the tab bar takes it to the verify-email screen.

## API (Phase 6 — medication, Premium)

| Method & path | Auth | Purpose |
|---|---|---|
| `GET /medications` | verified | List (kept visible after a plan lapses) |
| `POST /medications` · `PATCH/GET /medications/{id}` | Premium | Create / edit; instructions stored verbatim |
| `POST /medications/{id}/discontinue` · `/resume` | Premium | Stop future doses & reminders, keep history |
| `DELETE /medications/{id}` | verified | Permanently delete it and its dose history (always allowed) |
| `GET /medications/schedule?from&to` | Premium | Every dose in a local-date range with status (max 93 days) |
| `PUT /medications/{id}/doses` | Premium | Record or correct taken / skipped / missed for one dose time |
| `DELETE /medications/{id}/doses?scheduled_for=` | Premium | Undo a recorded outcome |
| `GET /medications/adherence?from&to` | Premium | Per-medication taken / skipped / missed / not-logged counts |

**Rules.** Schedules: daily, specific weekdays, every N days, or as needed; times are wall-clock in the
medication's IANA zone, so 08:00 stays 08:00 across DST (a time inside a spring-forward gap moves
forward by the gap; an ambiguous fall-back time is used once). A dose can only be recorded at a real
scheduled time (or "now or earlier" for as-needed), at most 30 days back. A dose with no record is
reported as **unrecorded** — never assumed taken and never counted as missed.

**Reminders** are on-device local notifications (`expo-notifications`) for the next 7 days, capped at
60 (iOS allows 64), re-planned whenever medications change or the Meds tab opens, and cleared on sign
out or when Premium lapses. The text is generic so medication names never appear on the lock screen.

## API (Phase 7 — fitness, Premium)

| Method & path | Auth | Purpose |
|---|---|---|
| `POST /workouts` | Premium | Start a GPS workout (idempotent on device `client_id`) |
| `POST /workouts/{id}/points` | Premium | Upload ≤ 500 fixes per batch (idempotent on `seq`); server recomputes distance |
| `POST /workouts/{id}/finish` · `/discard` | Premium | Finish (idempotent) or throw away |
| `POST /workouts/manual` | Premium | Log a workout without GPS |
| `GET /workouts?from&to` · `GET /workouts/{id}` | verified | List completed workouts / detail with accepted route |
| `DELETE /workouts/{id}` | verified | Delete workout and route (always allowed) |
| `GET/PUT/DELETE /health/connections/{provider}` | Premium (read/delete: verified) | Health Connect / Apple Health link, optional delete of imported data |
| `POST /health/import` | Premium | Upsert platform records, dedup on (user, source, external id) |
| `GET/POST/DELETE /fitness/goals` | Premium | Weekly / monthly distance, count or active-minute goals |
| `GET /fitness/summary?period=weekly|monthly` | Premium | Totals + goal progress for the current local week (Mon–Sun) or month |
| `GET/PUT /me/fitness-profile` | any user | Optional body weight, used only for calorie estimates |

**GPS rules (server-side, `services/geo.py`, mirrored in `mobile/src/lib/geo.ts` for the live view).**
Fixes worse than 35 m accuracy, implied speeds above 3.5 / 6 / 10 m/s (walk / jog / run), and moves under
3 m (jitter) are rejected; distance never bridges a pause (new segment). Active time excludes pauses
and is capped at wall-clock time. Calories = MET × weight × hours, shown only as an estimate and only
if the user gave a weight.

**Mobile tracking** (`expo-location` + `expo-task-manager`): a background location task (Android
foreground service with a visible notification, iOS background location indicator) appends every fix
to a persisted buffer first, then uploads in batches; offline gaps and retries are safe. If background
permission is refused it falls back to foreground-only updates and tells the user to keep the app
open. Requires a development build.

**Not yet done:** reading workouts from Health Connect / Apple Health on the phone (needs the native
health modules and a device to test). The backend import and connection endpoints are ready for it.

## API (Phase 8 — weather)

| Method & path | Auth | Purpose |
|---|---|---|
| `GET /weather/current?lat&lon` | verified (Free) | Current conditions + outdoor rating + hot-weather hydration tip |
| `GET /weather/forecast?lat&lon&hours` | Premium | 3-hourly forecast (≤ 120 h), each step rated for outdoor exercise, plus the best daylight slot |
| `GET /weather/places?q=` | verified | Town/city search (OpenWeather geocoding) |
| `GET/PUT/DELETE /me/weather-location` | verified | Saved location, stored at 2 dp (~1 km) |

Without `lat`/`lon` the saved location is used (409 `no_location` if none). Ad-hoc coordinates are
rounded and never stored on the profile. OpenWeather (free plan: `/data/2.5/weather`,
`/data/2.5/forecast`, `/geo/1.0/direct`) is called only by the backend; responses are cached in
`weather_cache` per rounded location (current 10 min, forecast 30 min, places 7 days). If OpenWeather
is unreachable the last copy is served for up to 6 h with `stale: true`, then 503 `weather_unavailable`.

**Outdoor rating** (`services/weather_rules.py`, pure): starts at 100 and subtracts for thunder
(always "poor"), rain/drizzle/chance of rain, snow, fog, heat (≥ 30 / ≥ 35 °C feels-like), cold
(≤ 3 / ≤ −5 °C), wind (≥ 9 / ≥ 14 m/s) and darkness; ≥ 70 good, ≥ 40 fair, else poor, with
plain-language reasons. Phase 9's recommendation engine reuses it.

**Mobile:** a weather chip on the Water tab (with a hot-day hydration tip) and a weather card on the
Move tab (forecast strip and "best time to get outside" for Premium). Location comes from a one-off
low-accuracy GPS read or a place search, rounded on the device before it's sent. Guests see a
labelled sample; tapping it opens Login/Register.

## API (Phase 9 — calendar & recommendations)

| Method & path | Auth | Purpose |
|---|---|---|
| `GET /calendar/status` | verified | Connected? free/busy and add-event permission |
| `POST /calendar/connect` | verified (Free) | Google consent URL (free/busy scope only), state + PKCE |
| `GET /calendar/oauth/callback` | Google redirect | Single-use state check, code exchange, encrypted token storage → app deep link |
| `DELETE /calendar` | verified | Revoke at Google and delete the stored connection |
| `GET /calendar/free-slots?date` | verified (Free) | Free time in the waking day (calendar busy blocks removed if connected) |
| `GET /recommendations?date` | verified | Water breaks (all plans) + walk/jog/run ideas (Premium) with reasons |
| `POST /recommendations/{id}/dismiss` | verified | Hide a suggestion |
| `POST /recommendations/{id}/schedule` | Premium | Create a Google Calendar event — only on this explicit request; idempotent. 409 `needs_calendar_permission` + `auth_url` triggers incremental consent |
| `GET/PATCH /me/scheduling-preferences` | verified | Wake/bed time, working hours, shortest useful slot, favourite activities & times |

**Engine** (`services/scheduling.py`, pure): free slots = waking day − busy blocks − the past, ≥ the
user's minimum. Water breaks go at slot starts, ≥ 90 min apart, max 4. Premium activity ideas are
tried every 30 min inside slots outside working hours, scored by the Phase 8 outdoor rating
(+15 for the user's favourite time band); "poor" weather is never suggested; the best three
non-overlapping ideas are kept. Without a forecast the idea is still offered and says so. Free users
are told how many ideas Premium would show. Refreshing replaces only unanswered suggestions —
scheduled/dismissed ones are kept and never duplicated.

Errors may now carry extra fields alongside `code`/`message` (e.g. `auth_url`).
