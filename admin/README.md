# LifePulse Admin

Owner/administrator dashboard for LifePulse. A separate web app that talks to the existing FastAPI
backend (`../backend`) over protected REST endpoints under `/api/v1/admin`. It has no database of its
own and never sees raw health records; feature pages show aggregates only.

**Stack:** React 19 · Vite · TypeScript · Tailwind CSS 4 · React Router · Recharts · Lucide · Vitest + Testing Library

## Run locally

```bash
cd admin
npm install
copy .env.example .env.local     # cp on macOS/Linux; set VITE_API_URL if the API isn't on :8000
npm run dev                      # http://localhost:5174
npm test                         # component + navigation tests
npm run typecheck
npm run build                    # production bundle in dist/
```

`/ui` (not in the sidebar) shows the design system: buttons, badges, KPI cards, date filter and the
loading / empty / error states.

## Docker

`docker compose up --build admin` from the repository root serves the built bundle with nginx on
http://localhost:8080. Pass `--build-arg VITE_API_URL=https://api.example.com` for other environments.

## Structure

```
src/
  nav.ts                 sidebar sections, routes, required permission per page (single source of truth)
  components/ui/         design system (Button, Card, Badge, KpiCard, states, DateRangeFilter)
  components/layout/     AppShell, Sidebar (collapsible), Topbar (search, notifications, account), Breadcrumbs
  pages/                 one page per section
  __tests__/             Vitest tests
```

## Design rules

- Colours, radii and shadows come from the tokens in `src/index.css` (`brand-*` emerald, `ink-*` charcoal).
- A figure with no data shows "—", never 0. A section without a backend yet says so.
- No sample or demo numbers anywhere in the UI.

## Status

| Phase | Status |
|---|---|
| 2. Frontend structure, navigation, design system | ✅ Done |
| 3. Admin authentication & backend authorisation | Planned |
| 4–10. Data pages | Planned |
