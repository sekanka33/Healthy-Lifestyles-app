import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { vi } from 'vitest';
import { AppRoutes } from '../App';
import { AuthProvider, type AdminMe } from '../lib/auth';

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
