/**
 * Typed client for the FastAPI backend.
 *
 * - Access token: memory only (15 min). Refresh token: secure storage.
 * - On 401 the client refreshes once and retries. Refreshes are single-flight: the server treats
 *   reuse of a rotated refresh token as theft, so two parallel refreshes would sign the user out.
 */
import { Platform } from 'react-native';

import { deleteSecret, getSecret, setSecret } from './secure-storage';

const DEFAULT_URL = Platform.OS === 'android' ? 'http://10.0.2.2:8000' : 'http://localhost:8000';
export const API_URL = (process.env.EXPO_PUBLIC_API_URL || DEFAULT_URL).replace(/\/$/, '');

const REFRESH_KEY = 'hl.refresh_token';

// ------------------------------------------------------------------ types (mirror app/schemas)

export type User = {
  id: string;
  email: string;
  first_name: string;
  last_name: string | null;
  email_verified: boolean;
  timezone: string;
  locale: string;
  units: 'metric' | 'imperial';
  plan: 'free' | 'premium';
  created_at: string;
};

export type TokenPair = { access_token: string; refresh_token: string; expires_in: number };
export type Session = TokenPair & { user: User };

export type HydrationEntry = {
  id: string;
  client_id: string;
  volume_ml: number;
  consumed_at: string;
  source: string;
  deleted: boolean;
};

export type DaySummary = {
  date: string;
  total_ml: number;
  goal_ml: number;
  progress: number;
  goal_met: boolean;
};

export type DayDetail = DaySummary & { timezone: string; entries: HydrationEntry[] };
export type History = { timezone: string; days: DaySummary[] };
export type Goal = { daily_goal_ml: number; effective_from: string | null };

export type Entitlement = {
  status: 'active' | 'grace_period' | 'billing_issue' | 'cancelled' | 'expired' | 'refunded';
  product_id: string | null;
  store: string | null;
  expires_at: string | null;
  will_renew: boolean;
  environment: string;
  last_verified_at: string | null;
};
export type BillingStatus = { plan: 'free' | 'premium'; entitlement: Entitlement | null };
export type Payment = {
  id: string;
  provider: string;
  product_id: string;
  kind: string;
  status: string;
  amount: string | null; // decimal string, exactly as verified
  currency: string | null;
  purchased_at: string;
  period_end: string | null;
  environment: string;
  receipt_number: string | null;
  has_receipt: boolean;
};

export type ScheduleType = 'daily' | 'specific_days' | 'every_n_days' | 'as_needed';
export type Medication = {
  id: string;
  name: string;
  dosage_instructions: string;
  notes: string | null;
  schedule_type: ScheduleType;
  times: string[];
  days_of_week: number[] | null;
  interval_days: number | null;
  timezone: string;
  start_date: string;
  end_date: string | null;
  reminders_enabled: boolean;
  discontinued_at: string | null;
  active: boolean;
  created_at: string;
};
export type MedicationInput = Partial<Omit<Medication, 'id' | 'discontinued_at' | 'active' | 'created_at'>>;
export type DoseState = 'taken' | 'skipped' | 'missed' | 'upcoming' | 'unrecorded';
export type ScheduledDose = {
  medication_id: string;
  medication_name: string;
  dosage_instructions: string;
  scheduled_for: string;
  status: DoseState;
  recorded_at: string | null;
  note: string | null;
};
export type AdherenceRow = {
  medication_id: string;
  medication_name: string;
  scheduled: number;
  taken: number;
  skipped: number;
  missed: number;
  unrecorded: number;
  as_needed_taken: number;
  adherence: number | null;
};

// ------------------------------------------------------------------ errors

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: { loc: (string | number)[]; msg: string }[],
  ) {
    super(message);
  }

  /** True when the request never reached the server (offline, DNS, timeout). */
  get isNetwork() {
    return this.status === 0;
  }

  /** A human message, using the first validation error when there is one. */
  get userMessage() {
    if (this.code === 'validation_error' && this.details?.length) {
      return this.details[0].msg.replace(/^Value error, /, '');
    }
    return this.message || 'Something went wrong.';
  }
}

// ------------------------------------------------------------------ token state

let accessToken: string | null = null;
let refreshInFlight: Promise<boolean> | null = null;
let onSessionLost: (() => void) | null = null;

export function setSessionLostHandler(fn: (() => void) | null) {
  onSessionLost = fn;
}

export async function saveTokens(t: TokenPair) {
  accessToken = t.access_token;
  await setSecret(REFRESH_KEY, t.refresh_token);
}

export async function clearTokens() {
  accessToken = null;
  await deleteSecret(REFRESH_KEY);
}

export async function hasStoredSession() {
  return (await getSecret(REFRESH_KEY)) !== null;
}

/** Exchanges the stored refresh token. Returns false if the session is gone. */
export function refreshSession(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      const refresh = await getSecret(REFRESH_KEY);
      if (!refresh) return false;
      try {
        const tokens = await raw<TokenPair>('POST', '/auth/refresh', { refresh_token: refresh });
        await saveTokens(tokens);
        return true;
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) {
          await clearTokens();
          return false;
        }
        throw e; // offline etc. — keep the stored token and try again later
      }
    })().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

// ------------------------------------------------------------------ requests

async function raw<T>(method: string, path: string, body?: unknown, token?: string | null): Promise<T> {
  let res: Response;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    res = await fetch(`${API_URL}/api/v1${path}`, {
      method,
      headers: {
        Accept: 'application/json',
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } catch {
    throw new ApiError(0, 'network_error', "Can't reach the server. Check your connection.");
  } finally {
    clearTimeout(timer);
  }
  if (res.status === 204) return undefined as T;
  const json = await res.json().catch(() => null);
  if (!res.ok) {
    const err = json?.error ?? {};
    throw new ApiError(res.status, err.code ?? 'http_error', err.message ?? `Request failed (${res.status})`, err.details);
  }
  return json as T;
}

/** Authenticated request with transparent refresh-and-retry. */
async function authed<T>(method: string, path: string, body?: unknown): Promise<T> {
  if (!accessToken && !(await refreshSession())) {
    onSessionLost?.();
    throw new ApiError(401, 'not_authenticated', 'Please sign in.');
  }
  try {
    return await raw<T>(method, path, body, accessToken);
  } catch (e) {
    if (!(e instanceof ApiError) || e.status !== 401) throw e;
    if (!(await refreshSession())) {
      onSessionLost?.();
      throw e;
    }
    return raw<T>(method, path, body, accessToken);
  }
}

// ------------------------------------------------------------------ endpoints

export const api = {
  register: (b: { email: string; password: string; first_name: string; last_name?: string; timezone: string }) =>
    raw<Session>('POST', '/auth/register', b),
  login: (email: string, password: string) => raw<Session>('POST', '/auth/login', { email, password }),
  logout: async () => {
    const refresh = await getSecret(REFRESH_KEY);
    if (refresh) await raw<void>('POST', '/auth/logout', { refresh_token: refresh }).catch(() => undefined);
    await clearTokens();
  },
  verifyEmail: (code: string) => authed<User>('POST', '/auth/verify-email', { code }),
  resendVerification: () => authed<{ status: string }>('POST', '/auth/resend-verification'),
  forgotPassword: (email: string) => raw<{ status: string }>('POST', '/auth/forgot-password', { email }),
  resetPassword: (email: string, code: string, new_password: string) =>
    raw<void>('POST', '/auth/reset-password', { email, code, new_password }),
  changePassword: (current_password: string, new_password: string) =>
    authed<TokenPair>('POST', '/auth/change-password', { current_password, new_password }),

  me: () => authed<User>('GET', '/me'),
  updateMe: (b: Partial<Pick<User, 'first_name' | 'last_name' | 'timezone' | 'units' | 'locale'>>) =>
    authed<User>('PATCH', '/me', b),

  today: () => authed<DayDetail>('GET', '/hydration/today'),
  history: (from?: string, to?: string) => {
    const q = new URLSearchParams();
    if (from) q.set('from', from);
    if (to) q.set('to', to);
    const qs = q.toString();
    return authed<History>('GET', `/hydration/history${qs ? `?${qs}` : ''}`);
  },
  addEntry: (b: { client_id: string; volume_ml: number; consumed_at: string; source?: 'app' | 'reminder' }) =>
    authed<HydrationEntry>('POST', '/hydration/entries', b),
  deleteEntry: (clientId: string) => authed<HydrationEntry>('DELETE', `/hydration/entries/${clientId}`),
  goal: () => authed<Goal>('GET', '/hydration/goal'),
  setGoal: (daily_goal_ml: number) => authed<Goal>('PUT', '/hydration/goal', { daily_goal_ml }),

  billingStatus: () => authed<BillingStatus>('GET', '/billing/status'),
  billingSync: () => authed<BillingStatus>('POST', '/billing/sync'),
  payments: () => authed<Payment[]>('GET', '/billing/transactions'),

  medications: () => authed<Medication[]>('GET', '/medications'),
  medication: (id: string) => authed<Medication>('GET', `/medications/${id}`),
  createMedication: (b: MedicationInput) => authed<Medication>('POST', '/medications', b),
  updateMedication: (id: string, b: MedicationInput) => authed<Medication>('PATCH', `/medications/${id}`, b),
  discontinueMedication: (id: string) => authed<Medication>('POST', `/medications/${id}/discontinue`),
  resumeMedication: (id: string) => authed<Medication>('POST', `/medications/${id}/resume`),
  deleteMedication: (id: string) => authed<void>('DELETE', `/medications/${id}`),
  medicationSchedule: (from?: string, to?: string) => {
    const q = new URLSearchParams();
    if (from) q.set('from', from);
    if (to) q.set('to', to);
    const qs = q.toString();
    return authed<ScheduledDose[]>('GET', `/medications/schedule${qs ? `?${qs}` : ''}`);
  },
  recordDose: (id: string, scheduled_for: string, status: 'taken' | 'skipped' | 'missed') =>
    authed<unknown>('PUT', `/medications/${id}/doses`, { scheduled_for, status }),
  clearDose: (id: string, scheduled_for: string) =>
    authed<void>('DELETE', `/medications/${id}/doses?scheduled_for=${encodeURIComponent(scheduled_for)}`),
  adherence: () => authed<{ from_date: string; to_date: string; medications: AdherenceRow[] }>('GET', '/medications/adherence'),
};
