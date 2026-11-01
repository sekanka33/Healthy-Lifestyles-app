/**
 * Google Calendar consent runs in a secure browser session (ASWebAuthenticationSession / Custom Tabs).
 * The backend does the code exchange and redirects to `healthylifestyles://calendar-connected?status=…`,
 * which closes the session. Tokens never touch the app.
 */
import * as WebBrowser from 'expo-web-browser';

import { api } from './api';

const RETURN_URL = 'healthylifestyles://calendar-connected';

export type ConnectOutcome = 'ok' | 'denied' | 'cancelled' | 'error';

export async function runGoogleConsent(authUrl?: string): Promise<ConnectOutcome> {
  const url = authUrl ?? (await api.connectCalendar()).auth_url;
  const result = await WebBrowser.openAuthSessionAsync(url, RETURN_URL);
  if (result.type !== 'success') return 'cancelled';
  const status = new URL(result.url.replace('healthylifestyles://', 'https://app/')).searchParams.get('status');
  return status === 'ok' || status === 'denied' ? status : 'error';
}

export const CONNECT_MESSAGES: Record<ConnectOutcome, string | null> = {
  ok: null,
  denied: 'Calendar access wasn’t granted. You can try again any time.',
  cancelled: null,
  error: 'Couldn’t connect Google Calendar. Please try again.',
};
