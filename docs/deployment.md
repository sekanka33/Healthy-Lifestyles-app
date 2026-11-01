# Deployment

## What runs in production
| Process | Command | Notes |
|---|---|---|
| API | `uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --workers 2` (image default) | Stateless; scale horizontally |
| Worker | `python -m app.worker` | Jobs + report scheduler + clean-up. Run 1+; safe in parallel (`SKIP LOCKED`) |
| Migrations | `alembic upgrade head` | Run once per release, **before** new API/worker versions start |
| PostgreSQL 16+ | managed (Neon, Supabase, RDS, Cloud SQL…) | Daily backups + point-in-time recovery |

The same Docker image (`backend/Dockerfile`, non-root user) serves all three.
`docker compose up --build` runs the whole stack locally; `docker compose --profile dev up --build`
adds Mailpit (inbox at http://localhost:8025).

Any container host works (Fly.io, Render, Railway, Cloud Run + a worker service, ECS). Put HTTPS in
front (the platform's load balancer) and set `FORWARDED_ALLOW_IPS` to that proxy so rate limits see
real client IPs.

## Environment (production refuses to start without the security-critical ones)
| Variable | Value |
|---|---|
| `ENVIRONMENT` | `production` (also hides `/docs`) |
| `PUBLIC_API_URL` | `https://api.your-domain` — used for email links; must be https |
| `DATABASE_URL` | `postgresql+psycopg://…` |
| `JWT_SECRET` | ≥ 32 random characters: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `TOKEN_ENCRYPTION_KEY` | Fernet key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` — **back it up**; losing it means everyone reconnects Google Calendar |
| `EMAIL_PROVIDER`, `RESEND_API_KEY`, `EMAIL_FROM` | `resend`, the key, an address on a verified sending domain (set SPF + DKIM) |
| `RESEND_WEBHOOK_SECRET` | Resend → Webhooks → endpoint `…/api/v1/email/webhooks/resend` → signing secret |
| `REVENUECAT_SECRET_API_KEY`, `REVENUECAT_WEBHOOK_AUTH` | see [subscriptions setup](subscriptions-setup.md) |
| `OPENWEATHER_API_KEY` | openweathermap.org |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` | see [calendar setup](calendar-setup.md); redirect = `https://api.your-domain/api/v1/calendar/oauth/callback` |
| `CORS_ORIGINS` | only if you host the web build, e.g. `https://app.your-domain` (comma-separated) |

Keep secrets in the hosting platform's secret store — never in the repo or the mobile app.

## Release checklist
1. CI green (`.github/workflows/ci.yml`: backend tests incl. migrations on PostgreSQL, mobile
   typecheck/lint/tests, Docker image build).
2. Back up the database, then `alembic upgrade head`.
3. Deploy API + worker; check `GET /health`.
4. Webhooks: RevenueCat "Send test event" → `{"status": "ignored"}`; Resend test event → 200.
5. Mobile: set `EXPO_PUBLIC_API_URL` in `mobile/eas.json` (`production`), confirm the bundle ID /
   package in `mobile/app.json`, then
   `npx eas-cli@latest build --profile production --platform all` and
   `npx eas-cli@latest submit --profile production`.
6. Store listings: privacy policy URL (`EXPO_PUBLIC_PRIVACY_URL`), terms (`EXPO_PUBLIC_TERMS_URL`),
   App Store "App Privacy" / Play "Data safety" answers (below), a reviewer demo account created with
   `python -m app.scripts.seed_demo_accounts` on a **staging** server (it refuses production), and
   Google's background-location declaration video.

## Store privacy answers (what the code actually collects)
| Data | Purpose | Linked to user | Shared with |
|---|---|---|---|
| Email, name | Account | Yes | Email provider (delivery only) |
| Health & fitness (water, medication, workouts) | App functionality | Yes | No one |
| Precise location | Workout routes, only while recording | Yes | No one |
| Approximate location (~1 km) | Weather | Yes | OpenWeather (rounded coordinates, no identity) |
| Calendar free/busy | Suggestions | Yes | No one (read from Google) |
| Purchases | Subscriptions | Yes | Apple / Google / RevenueCat |

No advertising, no tracking SDKs, no sale of data.

## Operations
- **Jobs:** `SELECT kind, status, count(*) FROM jobs GROUP BY 1, 2;` — `dead` jobs keep `last_error`.
  Retry one with `UPDATE jobs SET status = 'queued', attempts = 0 WHERE id = '…';`.
- **Email:** `email_messages.status` goes queued → accepted → delivered / bounced / complained.
- **Retention:** the worker deletes expired codes and OAuth states, old refresh tokens, rate-limit
  buckets and webhook logs older than 90 days every hour. Deleting an account cascades to all its data.
- **Logs** never contain passwords, tokens, codes, coordinates or health values.
