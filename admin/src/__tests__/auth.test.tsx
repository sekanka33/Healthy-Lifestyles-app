import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { ApiError, apiFetch } from '../lib/api';
import { validateLogin, validateCode } from '../pages/LoginPage';
import { validatePasswordChange } from '../pages/SecurityPage';
import { apiError, makeAdmin, mockApi, renderAt } from '../test/render';

const session = (admin = makeAdmin()) => ({
  status: 'ok', token: 'lpa_new-token', expires_at: '2026-11-09T22:00:00Z', idle_timeout_minutes: 30, admin,
});

async function fillLogin(email = 'owner@example.com', password = 'admin-password-long-enough') {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText('Email'), email);
  await user.type(screen.getByLabelText('Password'), password);
  await user.click(screen.getByRole('button', { name: 'Sign in' }));
  return user;
}

describe('access control', () => {
  it('sends signed-out visitors to the login page', async () => {
    renderAt('/payments');
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(screen.queryByRole('complementary', { name: 'Main navigation' })).not.toBeInTheDocument();
  });

  it('a stored but expired session is cleared with an explanation', async () => {
    sessionStorage.setItem('lp-admin.session', 'lpa_stale');
    renderAt('/', { handlers: { 'GET /auth/me': () => apiError(401, 'admin_not_authenticated', 'Please sign in.') } });
    expect(await screen.findByText(/Your session has ended/)).toBeInTheDocument();
    expect(sessionStorage.getItem('lp-admin.session')).toBeNull();
  });

  it('hides sections a role cannot use and blocks direct links to them', async () => {
    renderAt('/users', { admin: makeAdmin('finance') });
    expect(await screen.findByText("You don't have access to this page")).toBeInTheDocument();
    const nav = screen.getByRole('complementary', { name: 'Main navigation' });
    expect(within(nav).getByRole('link', { name: 'Payments & Revenue' })).toBeInTheDocument();
    expect(within(nav).queryByRole('link', { name: 'User Management' })).not.toBeInTheDocument();
    expect(within(nav).queryByRole('link', { name: 'Application Settings' })).not.toBeInTheDocument();
  });

  it('a support agent cannot see finance pages', async () => {
    renderAt('/payments', { admin: makeAdmin('support') });
    expect(await screen.findByText("You don't have access to this page")).toBeInTheDocument();
    const nav = screen.getByRole('complementary', { name: 'Main navigation' });
    expect(within(nav).queryByRole('link', { name: 'Payments & Revenue' })).not.toBeInTheDocument();
    expect(within(nav).getByRole('link', { name: 'Feedback & Support' })).toBeInTheDocument();
  });

  it('pending MFA setup confines the admin to the security page', async () => {
    renderAt('/', { admin: makeAdmin('owner', { mfa_required: true, mfa_setup_needed: true }) });
    expect(await screen.findByRole('heading', { level: 1, name: 'Security' })).toBeInTheDocument();
    expect(screen.getByText(/required on this server/)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Overview' })).not.toBeInTheDocument();
  });
});

describe('login', () => {
  it('validates the form before calling the API', async () => {
    const { api } = renderAt('/login');
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Sign in' }));
    expect(screen.getByText('Enter your email address.')).toBeInTheDocument();
    expect(screen.getByText('Enter your password.')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Email'), 'not-an-email');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(screen.getByText('Enter a valid email address.')).toBeInTheDocument();
    expect(api.calls).toHaveLength(0);
  });

  it('signs in and opens the dashboard', async () => {
    const { api } = renderAt('/login', { handlers: { 'POST /auth/login': () => ({ json: session() }) } });
    await fillLogin();
    expect(await screen.findByRole('heading', { level: 1, name: 'Overview' })).toBeInTheDocument();
    expect(screen.getByText('Thandi Owner')).toBeInTheDocument();
    expect(api.calls[0].body).toEqual({ email: 'owner@example.com', password: 'admin-password-long-enough' });
    expect(sessionStorage.getItem('lp-admin.session')).toBe('lpa_new-token');
  });

  it('shows the server message for wrong credentials', async () => {
    renderAt('/login', {
      handlers: { 'POST /auth/login': () => apiError(401, 'invalid_credentials', 'Email or password is incorrect.') },
    });
    await fillLogin();
    expect(await screen.findByRole('alert')).toHaveTextContent('Email or password is incorrect.');
  });

  it('explains rate limiting', async () => {
    renderAt('/login', { handlers: { 'POST /auth/login': () => apiError(429, 'rate_limited', 'Too many attempts.') } });
    await fillLogin();
    expect(await screen.findByRole('alert')).toHaveTextContent(/wait a few minutes/);
  });

  it('asks for the authenticator code when MFA is on', async () => {
    const { api } = renderAt('/login', {
      handlers: {
        'POST /auth/login': () => ({ json: { status: 'mfa_required', mfa_token: 'challenge-token-xxxxxxxxxx' } }),
        'POST /auth/mfa/verify': (body) =>
          (body as { code: string }).code === '123456' ? { json: session() } : apiError(401, 'invalid_mfa_code', "That code isn't right."),
      },
    });
    const user = await fillLogin();
    await screen.findByRole('heading', { name: 'Two-step verification' });

    await user.type(screen.getByLabelText('Verification code'), '12');
    await user.click(screen.getByRole('button', { name: 'Verify' }));
    expect(screen.getByText(/Enter the 6-digit code/, { selector: 'p.text-xs' })).toBeInTheDocument();

    await user.clear(screen.getByLabelText('Verification code'));
    await user.type(screen.getByLabelText('Verification code'), '000000');
    await user.click(screen.getByRole('button', { name: 'Verify' }));
    expect(await screen.findByRole('alert')).toHaveTextContent("That code isn't right.");

    await user.clear(screen.getByLabelText('Verification code'));
    await user.type(screen.getByLabelText('Verification code'), '123 456');
    await user.click(screen.getByRole('button', { name: 'Verify' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Overview' })).toBeInTheDocument();
    expect(api.calls.at(-1)?.body).toEqual({ mfa_token: 'challenge-token-xxxxxxxxxx', code: '123456' });
  });

  it('signs out from the account menu', async () => {
    const { api } = renderAt('/', { admin: makeAdmin() });
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Account menu' }));
    await user.click(screen.getByRole('menuitem', { name: /Sign out/ }));
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(sessionStorage.getItem('lp-admin.session')).toBeNull();
    await waitFor(() => expect(api.calls.map((c) => c.key)).toContain('POST /auth/logout'));
  });

  it('a 401 on any request signs the admin out', async () => {
    const { api } = renderAt('/account/security', {
      admin: makeAdmin(),
      handlers: { 'POST /auth/mfa/setup': () => apiError(401, 'admin_not_authenticated', 'Session ended') },
    });
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Set up two-step verification' }));
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(api.calls.some((c) => c.key === 'POST /auth/mfa/setup')).toBe(true);
  });
});

describe('security page', () => {
  it('enrols MFA with the shown key', async () => {
    const enabled = makeAdmin('owner', { mfa_enabled: true });
    renderAt('/account/security', {
      admin: makeAdmin(),
      handlers: {
        'POST /auth/mfa/setup': () => ({ json: { secret: 'ABCDEFGHIJKLMNOP', otpauth_uri: 'otpauth://totp/x' } }),
        'POST /auth/mfa/enable': () => ({ json: enabled }),
      },
    });
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Set up two-step verification' }));
    expect(await screen.findByTestId('mfa-secret')).toHaveTextContent('ABCD EFGH IJKL MNOP');
    await user.type(screen.getByLabelText('Code from the app'), '654321');
    await user.click(screen.getByRole('button', { name: 'Turn on' }));
    expect(await screen.findByText('On')).toBeInTheDocument();
    expect(screen.queryByTestId('mfa-secret')).not.toBeInTheDocument();
  });

  it('changes the password and adopts the new session', async () => {
    const { api } = renderAt('/account/security', {
      admin: makeAdmin(),
      handlers: { 'POST /auth/change-password': () => ({ json: session() }) },
    });
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText('Current password'), 'old-password-123');
    await user.type(screen.getByLabelText('New password'), 'brand-new-password');
    await user.type(screen.getByLabelText('Confirm new password'), 'brand-new-password');
    await user.click(screen.getByRole('button', { name: 'Change password' }));
    expect(await screen.findByText('Password changed.')).toBeInTheDocument();
    expect(sessionStorage.getItem('lp-admin.session')).toBe('lpa_new-token');
    expect(api.calls.at(-1)?.body).toEqual({ current_password: 'old-password-123', new_password: 'brand-new-password' });
  });
});

describe('validation helpers', () => {
  it('login', () => {
    expect(validateLogin('', '')).toEqual({ email: 'Enter your email address.', password: 'Enter your password.' });
    expect(validateLogin('a@b.co', 'x')).toEqual({});
  });
  it('code', () => {
    expect(validateCode('123 456')).toBeNull();
    expect(validateCode('12345a')).not.toBeNull();
  });
  it('password change', () => {
    expect(validatePasswordChange('', 'x', 'x')).toMatch(/current/);
    expect(validatePasswordChange('a', 'short', 'short')).toMatch(/12 characters/);
    expect(validatePasswordChange('a', 'long-enough-pass', 'different-pass!')).toMatch(/match/);
    expect(validatePasswordChange('long-enough-pass', 'long-enough-pass', 'long-enough-pass')).toMatch(/different/);
    expect(validatePasswordChange('a', 'long-enough-pass', 'long-enough-pass')).toBeNull();
  });
});

describe('api client', () => {
  it('sends the bearer token and parses the error shape', async () => {
    const { calls } = mockApi({ 'GET /roles': () => apiError(403, 'forbidden', "Your role doesn't allow this action.") });
    const err = await apiFetch('/roles', { token: 'lpa_abc' }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 403, code: 'forbidden', message: "Your role doesn't allow this action." });
    expect(calls[0].headers.Authorization).toBe('Bearer lpa_abc');
  });

  it('reports network failures plainly', async () => {
    const { fetchMock } = mockApi({});
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    await expect(apiFetch('/auth/me')).rejects.toMatchObject({ code: 'network_error' });
  });
});
