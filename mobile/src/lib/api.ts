/**
 * Typed client for the FastAPI backend.
 *
 * - Access token: memory only (15 min). Refresh token: secure storage.
 * - On 401 the client refreshes once and retries. Refreshes are single-flight: the server treats
 *   reuse of a rotated refresh token as theft, so two parallel refreshes would sign the user out.
 */
import Constants from 'expo-constants';
import { Platform } from 'react-native';

import { deleteSecret, getSecret, setSecret } from './secure-storage';

/**
 * Where the backend is.
 * 1. EXPO_PUBLIC_API_URL if set (staging / production builds, or to override).
 * 2. In development: the computer running the Expo dev server, port 8000. Expo tells us its address
 *    (`hostUri`, e.g. 192.168.18.67:8081), which a real phone on the same Wi-Fi can reach — so no setup.
 * 3. Fallbacks for emulators/simulators.
 */
function devServerHost(): string | null {
  if (!__DEV__) return null;
  if (Platform.OS === 'web') return typeof window !== 'undefined' ? window.location.hostname || null : null;
  const hostUri = Constants.expoConfig?.hostUri;
  return hostUri ? hostUri.split(':')[0] : null;
}

const FALLBACK_URL = Platform.OS === 'android' ? 'http://10.0.2.2:8000' : 'http://localhost:8000';
const devHost = devServerHost();
export const API_URL = (process.env.EXPO_PUBLIC_API_URL || (devHost ? `http://${devHost}:8000` : FALLBACK_URL)).replace(/\/$/, '');

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

export type Activity = 'walking' | 'jogging' | 'running';
export type Workout = {
  id: string;
  client_id: string;
  activity_type: Activity;
  source: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  active_duration_s: number;
  distance_m: number;
  pace_s_per_km: number | null;
  calories_kcal_estimate: number | null;
  steps: number | null;
  notes: string | null;
  point_count: number;
};
export type WorkoutDetail = Workout & { route: { lat: number; lon: number; segment: number }[] };
export type WorkoutPointIn = {
  seq: number; segment: number; recorded_at: string; lat: number; lon: number;
  altitude_m?: number | null; accuracy_m?: number | null; speed_mps?: number | null;
};
export type GoalProgress = {
  id: string; metric: 'distance_km' | 'workout_count' | 'active_minutes'; period: 'weekly' | 'monthly';
  target_value: number; activity_type: Activity | null; current_value: number; progress: number;
  period_start: string; period_end: string;
};
export type FitnessSummary = {
  period: 'weekly' | 'monthly'; period_start: string; period_end: string; timezone: string; workouts: number;
  distance_km: number; active_minutes: number; calories_kcal_estimate: number | null; goals: GoalProgress[];
};

export type Outdoor = { score: number; label: 'good' | 'fair' | 'poor'; reasons: string[] };
export type WeatherCondition = { code: number; main: string; description: string; icon: string };
export type CurrentWeather = {
  lat: number; lon: number; place_name: string | null; observed_at: string | null;
  temp_c: number | null; feels_like_c: number | null; humidity: number | null; wind_mps: number | null;
  wind_gust_mps: number | null; rain_mm_1h: number | null; condition: WeatherCondition;
  sunrise: string | null; sunset: string | null; is_day: boolean; outdoor: Outdoor;
  hydration_tip: string | null; stale: boolean;
};
export type ForecastStep = {
  at: string; temp_c: number | null; feels_like_c: number | null; humidity: number | null; wind_mps: number | null;
  pop: number | null; rain_mm: number | null; condition: WeatherCondition; is_day: boolean; outdoor: Outdoor;
};
export type Forecast = { lat: number; lon: number; stale: boolean; sunrise: string | null; sunset: string | null; steps: ForecastStep[]; best_time: string | null };
export type Place = { name: string; lat: number; lon: number };
export type WeatherLocation = { lat: number | null; lon: number | null; name: string | null };

export type CalendarStatus = { connected: boolean; status: string | null; can_read_free_busy: boolean; can_add_events: boolean };
export type FreeSlots = { date: string; timezone: string; calendar_used: boolean; slots: { start: string; end: string; minutes: number }[] };
export type Recommendation = {
  id: string; kind: 'hydration' | Activity; title: string; reason: string; start: string; end: string;
  status: 'suggested' | 'accepted' | 'dismissed' | 'scheduled'; weather: { temp_c: number; outdoor: Outdoor } | null;
};
export type Recommendations = { date: string; timezone: string; calendar_used: boolean; items: Recommendation[]; premium_ideas_available: number };
export type SchedulingPrefs = {
  working_hours_start: string | null; working_hours_end: string | null; sleep_start: string; sleep_end: string;
  min_free_slot_minutes: number; preferred_activities: Activity[]; preferred_activity_times: ('morning' | 'afternoon' | 'evening')[];
};

// ------------------------------------------------------------------ errors

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: { loc: (string | number)[]; msg: string }[],
    /** Any extra fields the server attached to the error (e.g. `auth_url`). */
    public extra: Record<string, unknown> = {},
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
    throw new ApiError(0, 'network_error', __DEV__
      ? `Can't reach the server at ${API_URL}. Is the backend running (uvicorn … --host 0.0.0.0) and on the same Wi-Fi?`
      : "Can't reach the server. Check your connection.");
  } finally {
    clearTimeout(timer);
  }
  if (res.status === 204) return undefined as T;
  const json = await res.json().catch(() => null);
  if (!res.ok) {
    const err = json?.error ?? {};
    const { code, message, details, ...extra } = err;
    throw new ApiError(res.status, code ?? 'http_error', message ?? `Request failed (${res.status})`, details, extra);
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

  workouts: () => authed<Workout[]>('GET', '/workouts'),
  workout: (id: string) => authed<WorkoutDetail>('GET', `/workouts/${id}`),
  startWorkout: (b: { client_id: string; activity_type: Activity; started_at: string }) => authed<Workout>('POST', '/workouts', b),
  addWorkoutPoints: (id: string, points: WorkoutPointIn[]) =>
    authed<{ added: number; distance_m: number }>('POST', `/workouts/${id}/points`, { points }),
  finishWorkout: (id: string, b: { ended_at: string; active_duration_s: number }) => authed<Workout>('POST', `/workouts/${id}/finish`, b),
  discardWorkout: (id: string) => authed<Workout>('POST', `/workouts/${id}/discard`),
  deleteWorkout: (id: string) => authed<void>('DELETE', `/workouts/${id}`),
  manualWorkout: (b: { client_id: string; activity_type: Activity; started_at: string; active_duration_s: number; distance_m: number }) =>
    authed<Workout>('POST', '/workouts/manual', b),
  fitnessSummary: (period: 'weekly' | 'monthly' = 'weekly') => authed<FitnessSummary>('GET', `/fitness/summary?period=${period}`),
  addFitnessGoal: (b: { metric: GoalProgress['metric']; period: GoalProgress['period']; target_value: number }) =>
    authed<GoalProgress>('POST', '/fitness/goals', b),
  removeFitnessGoal: (id: string) => authed<void>('DELETE', `/fitness/goals/${id}`),
  fitnessProfile: () => authed<{ body_weight_kg: number | null }>('GET', '/me/fitness-profile'),
  setFitnessProfile: (body_weight_kg: number | null) => authed<{ body_weight_kg: number | null }>('PUT', '/me/fitness-profile', { body_weight_kg }),

  currentWeather: () => authed<CurrentWeather>('GET', '/weather/current'),
  forecast: (hours = 24) => authed<Forecast>('GET', `/weather/forecast?hours=${hours}`),
  searchPlaces: (q: string) => authed<Place[]>('GET', `/weather/places?q=${encodeURIComponent(q)}`),
  weatherLocation: () => authed<WeatherLocation>('GET', '/me/weather-location'),
  setWeatherLocation: (b: { lat: number; lon: number; name?: string | null }) => authed<WeatherLocation>('PUT', '/me/weather-location', b),
  clearWeatherLocation: () => authed<void>('DELETE', '/me/weather-location'),

  calendarStatus: () => authed<CalendarStatus>('GET', '/calendar/status'),
  connectCalendar: () => authed<{ auth_url: string }>('POST', '/calendar/connect'),
  disconnectCalendar: () => authed<void>('DELETE', '/calendar'),
  freeSlots: (date?: string) => authed<FreeSlots>('GET', `/calendar/free-slots${date ? `?date=${date}` : ''}`),
  recommendations: (date?: string) => authed<Recommendations>('GET', `/recommendations${date ? `?date=${date}` : ''}`),
  dismissRecommendation: (id: string) => authed<Recommendation>('POST', `/recommendations/${id}/dismiss`),
  scheduleRecommendation: (id: string) => authed<Recommendation>('POST', `/recommendations/${id}/schedule`),
  schedulingPrefs: () => authed<SchedulingPrefs>('GET', '/me/scheduling-preferences'),
  setSchedulingPrefs: (b: Partial<SchedulingPrefs>) => authed<SchedulingPrefs>('PATCH', '/me/scheduling-preferences', b),
};
