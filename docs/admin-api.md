# Admin API

The owner/admin dashboard (`admin/`) talks to the existing FastAPI backend under **`/api/v1/admin`**.
Same database, same error shape as the app API: `{"error": {"code", "message", "details"?}}`.

## Creating the first Owner

Run once on the server (or in the `api` container) after `alembic upgrade head`:

```bash
cd backend
python -m app.scripts.create_owner --email you@yourdomain.com --name "Your Name"
# docker compose run --rm api python -m app.scripts.create_owner --email ... --name "..."
```

- The password is typed at a hidden prompt, twice. It's never a command-line argument, so it can't end
  up in shell history. For unattended setup, `ADMIN_OWNER_PASSWORD` can be set for that one command.
- Minimum 12 characters, and it mustn't contain the email's name part.
- The script refuses to run if an Owner already exists, and writes an `admin.created` audit entry.
- Then sign in to the dashboard → **account menu → Security** → set up two-step verification.
  In production (`ENVIRONMENT=production`) this is **mandatory**: until it's done, the account can
  only reach the Security page, and every other admin endpoint answers `403 mfa_setup_required`.

**Lost access to the authenticator app?** There's no email-based reset (deliberately). Someone with
server access can clear it: `UPDATE admin_users SET mfa_enabled_at = NULL, mfa_secret_enc = NULL WHERE email = '…';`,
after which the account must enrol again at next sign-in.

## Sessions

| | |
|---|---|
| Token | Opaque `lpa_…` bearer token. Only its SHA-256 is stored (`admin_sessions`). |
| Lifetime | 30 min idle (`ADMIN_SESSION_IDLE_MINUTES`), 12 h absolute (`ADMIN_SESSION_MAX_HOURS`) |
| Revocation | Sign-out, password change (all sessions), enabling MFA (all other sessions), deactivating the admin |
| Separation | App JWTs are rejected by every admin route; admin tokens are rejected by every app route. Admin accounts live in `admin_users`, never in `users`. |
| Browser storage | `sessionStorage` (per tab, cleared when the browser closes); requests use `credentials: omit` |

## Authentication endpoints

| Method & path | Auth | Purpose |
|---|---|---|
| `POST /admin/auth/login` | — | `{email, password}` → `{status:"ok", token, expires_at, idle_timeout_minutes, admin}` or `{status:"mfa_required", mfa_token}`. Rate limited: 5 / 15 min per email, 20 / 15 min per IP |
| `POST /admin/auth/mfa/verify` | MFA challenge | `{mfa_token, code}` → session. Challenge lives 5 min and dies if the password changes; 5 attempts / 15 min |
| `POST /admin/auth/logout` | session | Revoke this session (204) |
| `GET /admin/auth/me` | session | Profile, role, permission list, MFA status |
| `POST /admin/auth/mfa/setup` | session | New TOTP secret + `otpauth://` URI (shown once; inactive until enabled) |
| `POST /admin/auth/mfa/enable` | session | `{code}` → turns MFA on, ends other sessions |
| `POST /admin/auth/mfa/disable` | session | `{password, code}`; refused (409) when MFA is required |
| `POST /admin/auth/change-password` | session | `{current_password, new_password}` → fresh session; all old ones revoked |
| `GET /admin/roles` | `admins.manage` | Role → permission matrix |

TOTP follows RFC 6238 (SHA-1, 6 digits, 30 s, ±1 step drift). A code's time step can be used only
once, so an observed code can't be replayed. Secrets are Fernet-encrypted (`TOKEN_ENCRYPTION_KEY`).

## Roles and permissions

Defined in `backend/app/core/admin_permissions.py` and enforced by `require_permission(...)` on every
admin route. The dashboard hides what a role can't use, but that's only a convenience.

| Permission | Owner | Admin | Support | Finance | Technical |
|---|:-:|:-:|:-:|:-:|:-:|
| dashboard.read | ✅ | ✅ | ✅ | ✅ | ✅ |
| users.read | ✅ | ✅ | ✅ | | |
| users.manage | ✅ | ✅ | | | |
| users.delete | ✅ | | | | |
| subscriptions.read | ✅ | ✅ | | ✅ | |
| payments.read | ✅ | | | ✅ | |
| plans.read | ✅ | ✅ | | ✅ | |
| plans.manage | ✅ | | | | |
| features.read | ✅ | ✅ | | | ✅ |
| emails.read | ✅ | ✅ | ✅ | | ✅ |
| emails.resend | ✅ | ✅ | | | |
| analytics.read | ✅ | ✅ | | ✅ | |
| reports.read / reports.export | ✅ | ✅ | | ✅ | |
| support.read / support.manage | ✅ | ✅ | ✅ | | |
| system.read | ✅ | ✅ | | | ✅ |
| audit.read | ✅ | | | | ✅ |
| settings.read | ✅ | ✅ | | | |
| settings.manage | ✅ | | | | |
| admins.manage | ✅ | | | | |

Revenue figures on the overview additionally require `payments.read`.

Error codes: `401 admin_not_authenticated` (no/expired/revoked session), `403 forbidden` (role),
`403 mfa_setup_required`, `401 invalid_credentials`, `401 invalid_mfa_code`, `401 mfa_challenge_expired`,
`429 rate_limited` (with `Retry-After`).

## Overview (Phase 4)

`GET /admin/overview?from=YYYY-MM-DD&to=YYYY-MM-DD` · permission `dashboard.read`

Inclusive UTC dates; default the last 30 days (today + 29). 422 `invalid_range` if `from > to`, `to`
is in the future, or the span exceeds 366 days. Returns `users`, `subscriptions`, `revenue`,
`series` (`user_growth`, `active_users`, `conversion_monthly`, `revenue_monthly`), `feature_usage`
and `recent_activity` (latest 20). `revenue` and `series.revenue_monthly` are `null` without
`payments.read`; payment items and amounts are left out of `recent_activity` too. Admin actions
appear only with `audit.read`. Emails in recent activity are masked (`a•••@example.com`).

| Figure | Definition |
|---|---|
| Registered users | Rows in `users` |
| Active users | Distinct users with an authenticated app request on a day in the range (`user_activity_days`, one row per user per UTC day). **Only tracked from the deployment of Phase 4 onwards**; `activity_tracked_since` says from when |
| Premium | Premium entitlement now active / grace period / cancelled-but-paid-up and not expired. Same rule as the app. `premium_promotional` counts unpaid grants within it |
| Free | Registered − Premium |
| Converted users / conversion rate | Users with ≥ 1 verified production payment (succeeded or later refunded) ÷ registered users |
| Revenue | `payment_transactions` with status `succeeded`, environment `production`, per currency. Refunds and sandbox excluded. **Never summed across currencies** |
| MRR | Auto-renewing paid production subscriptions: latest succeeded payment × 30.4375 ÷ its billing-period days, per currency |
| Cancellations / failed payments | RevenueCat `CANCELLATION` / `BILLING_ISSUE` webhook events received in the range (sandbox excluded) |
| Feature usage | Distinct users + record counts in the range: drinks logged (undone ones excluded), medication doses recorded, completed workouts. Counts only |

## Audit log

`audit_logs` is append-only. Each row: admin id, actor email snapshot (kept if the admin is deleted),
action, resource type and id, `details` (JSON, never passwords, codes, tokens or health data), IP,
timestamp. Recorded so far: `admin.login`, `admin.login_password_ok` (MFA pending),
`admin.login_failed` (with reason: `unknown_email` / `bad_password` / `inactive` / `bad_mfa_code`),
`admin.logout`, `admin.mfa_enabled`, `admin.mfa_disabled`, `admin.password_changed`, `admin.created`.
Later phases add user, subscription, pricing and settings actions.
