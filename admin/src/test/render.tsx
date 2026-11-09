import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { vi } from 'vitest';
import { AppRoutes } from '../App';
import { AuthProvider, type AdminMe } from '../lib/auth';
import type { Overview } from '../pages/OverviewPage';

/** Permission sets per role, mirroring backend/app/core/admin_permissions.py (kept in sync by hand for tests). */
export const ROLE_PERMISSIONS: Record<string, string[]> = {
  owner: [
    'dashboard.read', 'users.read', 'users.manage', 'users.delete', 'subscriptions.read', 'payments.read',
    'plans.read', 'plans.manage', 'features.read', 'emails.read', 'emails.resend', 'analytics.read',
    'reports.read', 'reports.export', 'support.read', 'support.manage', 'system.read', 'admins.manage',
    'audit.read', 'settings.read', 'settings.manage',
  ],
  finance: ['dashboard.read', 'subscriptions.read', 'payments.read', 'plans.read', 'analytics.read', 'reports.read', 'reports.export'],
  support: ['dashboard.read', 'users.read', 'support.read', 'support.manage', 'emails.read'],
};

export function makeAdmin(role = 'owner', overrides: Partial<AdminMe> = {}): AdminMe {
  return {
    id: '00000000-0000-0000-0000-000000000001',
    email: `${role}@example.com`,
    full_name: 'Thandi Owner',
    role,
    role_label: { owner: 'Owner', finance: 'Finance Manager', support: 'Support Agent' }[role] ?? role,
    permissions: ROLE_PERMISSIONS[role] ?? [],
    mfa_enabled: false,
    mfa_required: false,
    mfa_setup_needed: false,
    last_login_at: null,
    ...overrides,
  };
}

type Handler = (body: unknown, init: RequestInit) => { status?: number; json?: unknown };

/** Fake the admin API at the fetch level. Keys look like "POST /auth/login". Unmatched calls fail the test. */
export function mockApi(handlers: Record<string, Handler>) {
  const calls: { key: string; body: unknown; headers: Record<string, string> }[] = [];
  const fetchMock = vi.fn(async (url: string, init: RequestInit = {}) => {
    const path = new URL(url).pathname.replace('/api/v1/admin', '');
    const key = `${init.method ?? 'GET'} ${path}`;
    const body = init.body ? JSON.parse(init.body as string) : undefined;
    calls.push({ key, body, headers: (init.headers ?? {}) as Record<string, string> });
    const handler = handlers[key];
    if (!handler) throw new Error(`Unexpected API call: ${key}`);
    const { status = 200, json } = handler(body, init);
    return new Response(status === 204 ? null : JSON.stringify(json ?? {}), {
      status, headers: { 'Content-Type': 'application/json' },
    });
  });
  vi.stubGlobal('fetch', fetchMock);
  return { calls, fetchMock };
}

export const apiError = (status: number, code: string, message: string) => ({ status, json: { error: { code, message } } });

/** Render the app at `path`. With `admin`, start signed in as that admin (token in sessionStorage, /auth/me mocked). */
export function renderAt(path = '/', { admin, handlers = {} }: { admin?: AdminMe | null; handlers?: Record<string, Handler> } = {}) {
  if (admin) sessionStorage.setItem('lp-admin.session', 'lpa_test-token');
  const api = mockApi({
    ...(admin ? { 'GET /auth/me': () => ({ json: admin }) } : {}),
    'POST /auth/logout': () => ({ status: 204 }),
    'GET /overview': () => ({ json: emptyOverview() }),
    ...handlers,
  });
  const utils = render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  );
  return { ...utils, api };
}

/** What the API returns for an empty database (owner view). */
export function emptyOverview(): Overview {
  const days = ['2026-11-08', '2026-11-09'];
  return {
    range: { from: days[0], to: days[1] },
    generated_at: '2026-11-09T10:00:00Z',
    users: { total: 0, active_in_range: 0, activity_tracked_since: null, new_in_range: 0, new_this_month: 0, premium: 0, premium_promotional: 0, free: 0 },
    subscriptions: { premium_active: 0, converted_users: 0, conversion_rate: null, cancellations_in_range: 0, failed_payments_in_range: 0 },
    revenue: { by_currency: [], sandbox_transactions_excluded: 0 },
    series: {
      user_growth: days.map((date) => ({ date, new_users: 0, total_users: 0 })),
      active_users: days.map((date) => ({ date, active_users: 0 })),
      conversion_monthly: [{ month: '2026-11', registered_users: 0, converted_users: 0, rate: null }],
      revenue_monthly: [{ month: '2026-11', amounts: {} }],
    },
    feature_usage: [
      { feature: 'water', label: 'Water tracking', users: 0, records: 0, record_label: 'drinks logged' },
      { feature: 'medication', label: 'Medication', users: 0, records: 0, record_label: 'doses recorded' },
      { feature: 'fitness', label: 'Fitness', users: 0, records: 0, record_label: 'workouts completed' },
    ],
    recent_activity: [],
  };
}
