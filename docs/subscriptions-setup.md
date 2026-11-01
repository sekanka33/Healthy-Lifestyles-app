# Subscriptions setup (RevenueCat + App Store + Google Play)

Premium is **$11 USD / month**, sold through Apple and Google in-app billing (required for digital
subscriptions) with RevenueCat in front of both. The backend is the only thing that decides who is
Premium.

```
 Phone ──purchase──▶ App Store / Google Play
   │                         │
   │ POST /billing/sync      ▼
   └────────▶ Backend ◀── RevenueCat webhook (shared-secret header)
                 │
                 └── GET /v1/subscribers/{user id} (secret key) ──▶ RevenueCat
                     → writes subscription_entitlements (the source of truth)
```

## 1. Store products
- **App Store Connect** → your app → Subscriptions → create a group "Premium" and an
  auto-renewable subscription, e.g. product id `premium_monthly`, duration 1 month, price $10.99 or
  $11.99 tier (Apple uses price tiers — pick the closest, then set other countries). Add the review
  screenshot and description.
- **Google Play Console** → Monetize → Subscriptions → create `premium_monthly` with a monthly base
  plan at $11.00 USD (Play allows exact prices).

## 2. RevenueCat
1. Create a project; add the iOS app (App Store Connect API key / in-app purchase key) and the
   Android app (Play service-account JSON).
2. **Entitlements** → create `premium` (must match `REVENUECAT_PREMIUM_ENTITLEMENT`) and attach both
   store products.
3. **Offerings** → the `default` offering → a **Monthly** package containing both products.
4. **API keys** → copy the public iOS key (`appl_…`) and Android key (`goog_…`) into
   `mobile/.env.local`, and the **secret** key (`sk_…`) into `backend/.env` as
   `REVENUECAT_SECRET_API_KEY`. Never put the secret key in the app.
5. **Integrations → Webhooks** → URL `https://<your api>/api/v1/billing/webhooks/revenuecat`,
   Authorization header = the value of `REVENUECAT_WEBHOOK_AUTH` (generate a long random one).
   Use "Send test event": the API answers `{"status": "ignored"}` for TEST events.

The app identifies each user to RevenueCat with their account UUID, which is how webhooks map back
to accounts. Anonymous RevenueCat ids are ignored.

## 3. Testing
- Real purchases need a **development build** (`npx expo run:ios` / `run:android` or
  `eas build --profile development`). Expo Go only runs RevenueCat in preview mode.
- iOS: sandbox Apple account (App Store Connect → Users and Access → Sandbox). Renewals are
  accelerated (a month renews every ~5 minutes).
- Android: add license testers in Play Console; install the build from an internal testing track.
- Sandbox purchases are recorded with `environment = sandbox` and marked "Test" in the app and on
  receipts. They do unlock Premium — Apple's app reviewers buy in sandbox against your production
  backend.

## Status mapping

| RevenueCat says | Our status | Premium? |
|---|---|---|
| entitlement not expired, renewing | `active` | ✅ |
| not expired, auto-renew turned off | `cancelled` | ✅ until `expires_at` |
| expired, but in the store's billing grace period | `grace_period` | ✅ until grace ends |
| expired with a billing issue | `billing_issue` | ❌ |
| refunded | `refunded` | ❌ |
| expired | `expired` | ❌ |
