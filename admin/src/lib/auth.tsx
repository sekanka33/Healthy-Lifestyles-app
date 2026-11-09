import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ApiError, apiFetch, type RequestOptions } from './api';

export interface AdminMe {
  id: string;
  email: string;
  full_name: string;
  role: string;
  role_label: string;
  permissions: string[];
  mfa_enabled: boolean;
  mfa_required: boolean;
  mfa_setup_needed: boolean;
  last_login_at: string | null;
}

interface SessionOut { status: 'ok'; token: string; expires_at: string; idle_timeout_minutes: number; admin: AdminMe }
interface MfaChallengeOut { status: 'mfa_required'; mfa_token: string }

export type LoginResult = { kind: 'ok' } | { kind: 'mfa'; mfaToken: string };

type Status = 'loading' | 'signed_out' | 'signed_in';

interface AuthValue {
  status: Status;
  admin: AdminMe | null;
  /** Why the last session ended (shown on the login page), e.g. after an idle timeout. */
  notice: string | null;
  login: (email: string, password: string) => Promise<LoginResult>;
  verifyMfa: (mfaToken: string, code: string) => Promise<void>;
  logout: () => Promise<void>;
  can: (permission: string) => boolean;
  /** Authenticated request: a 401 signs the admin out. */
  request: <T>(path: string, opts?: Omit<RequestOptions, 'token'>) => Promise<T>;
  /** Replace the session (after a password change) or the profile (after MFA changes). */
  applySession: (s: SessionOut) => void;
  setAdmin: (a: AdminMe) => void;
}

const AuthContext = createContext<AuthValue | null>(null);

// sessionStorage: tab-scoped, gone when the browser closes. The server also enforces idle + absolute timeouts.
const TOKEN_KEY = 'lp-admin.session';
const store = {
  get: (): string | null => { try { return sessionStorage.getItem(TOKEN_KEY); } catch { return null; } },
  set: (t: string) => { try { sessionStorage.setItem(TOKEN_KEY, t); } catch { /* memory only */ } },
  clear: () => { try { sessionStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ } },
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const tokenRef = useRef<string | null>(store.get());
  const [status, setStatus] = useState<Status>(tokenRef.current ? 'loading' : 'signed_out');
  const [admin, setAdmin] = useState<AdminMe | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const signOutLocally = useCallback((message: string | null) => {
    tokenRef.current = null;
    store.clear();
    setAdmin(null);
    setNotice(message);
    setStatus('signed_out');
  }, []);

  const applySession = useCallback((s: SessionOut) => {
    tokenRef.current = s.token;
    store.set(s.token);
    setAdmin(s.admin);
    setNotice(null);
    setStatus('signed_in');
  }, []);

  const request = useCallback(async <T,>(path: string, opts: Omit<RequestOptions, 'token'> = {}): Promise<T> => {
    try {
      return await apiFetch<T>(path, { ...opts, token: tokenRef.current });
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) signOutLocally('Your session has ended. Please sign in again.');
      throw e;
    }
  }, [signOutLocally]);

  useEffect(() => {
    if (!tokenRef.current) return;
    let cancelled = false;
    apiFetch<AdminMe>('/auth/me', { token: tokenRef.current })
      .then((me) => { if (!cancelled) { setAdmin(me); setStatus('signed_in'); } })
      .catch((e) => {
        if (cancelled) return;
        signOutLocally(e instanceof ApiError && e.status === 401 ? 'Your session has ended. Please sign in again.' : null);
      });
    return () => { cancelled = true; };
  }, [signOutLocally]);

  const login = useCallback(async (email: string, password: string): Promise<LoginResult> => {
    const res = await apiFetch<SessionOut | MfaChallengeOut>('/auth/login', { method: 'POST', body: { email, password } });
    if (res.status === 'mfa_required') return { kind: 'mfa', mfaToken: res.mfa_token };
    applySession(res);
    return { kind: 'ok' };
  }, [applySession]);

  const verifyMfa = useCallback(async (mfaToken: string, code: string) => {
    applySession(await apiFetch<SessionOut>('/auth/mfa/verify', { method: 'POST', body: { mfa_token: mfaToken, code } }));
  }, [applySession]);

  const logout = useCallback(async () => {
    const token = tokenRef.current;
    signOutLocally(null);
    if (token) await apiFetch('/auth/logout', { method: 'POST', token }).catch(() => undefined);
  }, [signOutLocally]);

  const can = useCallback((p: string) => !!admin && !admin.mfa_setup_needed && admin.permissions.includes(p), [admin]);

  const value = useMemo<AuthValue>(
    () => ({ status, admin, notice, login, verifyMfa, logout, can, request, applySession, setAdmin }),
    [status, admin, notice, login, verifyMfa, logout, can, request, applySession],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
