import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, ReactNode, use, useCallback, useEffect, useMemo, useState } from 'react';

import { api, ApiError, clearTokens, hasStoredSession, refreshSession, saveTokens, setSessionLostHandler, User } from './api';
import { clearHydrationCache } from './hydration-store';
import { clearMedicationReminders } from './medication-reminders';
import { forgetPurchaser, identifyPurchaser } from './purchases';

const USER_CACHE_KEY = 'hl.user';

type Status = 'loading' | 'signedOut' | 'signedIn';

type AuthValue = {
  status: Status;
  user: User | null;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (b: { email: string; password: string; first_name: string; last_name?: string }) => Promise<void>;
  signOut: () => Promise<void>;
  setUser: (u: User) => void;
  reloadUser: () => Promise<void>;
};

const AuthContext = createContext<AuthValue | null>(null);

export function deviceTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>('loading');
  const [user, setUserState] = useState<User | null>(null);

  const setUser = useCallback((u: User) => {
    setUserState(u);
    void identifyPurchaser(u.id);
    AsyncStorage.setItem(USER_CACHE_KEY, JSON.stringify(u)).catch(() => undefined);
  }, []);

  const forgetSession = useCallback(async () => {
    await clearTokens();
    await AsyncStorage.removeItem(USER_CACHE_KEY).catch(() => undefined);
    await clearHydrationCache();
    await forgetPurchaser();
    await clearMedicationReminders().catch(() => undefined); // never remind a signed-out device
    setUserState(null);
    setStatus('signedOut');
  }, []);

  // Restore the session on launch. Offline launches use the cached profile.
  useEffect(() => {
    setSessionLostHandler(() => void forgetSession());
    (async () => {
      if (!(await hasStoredSession())) return setStatus('signedOut');
      try {
        if (!(await refreshSession())) return forgetSession();
        setUser(await api.me());
        setStatus('signedIn');
      } catch (e) {
        const cached = await AsyncStorage.getItem(USER_CACHE_KEY).catch(() => null);
        if (e instanceof ApiError && e.isNetwork && cached) {
          setUser(JSON.parse(cached));
          setStatus('signedIn');
        } else {
          await forgetSession();
        }
      }
    })();
    return () => setSessionLostHandler(null);
  }, [forgetSession, setUser]);

  const signIn = useCallback(async (email: string, password: string) => {
    const s = await api.login(email.trim(), password);
    await saveTokens(s);
    setUser(s.user);
    setStatus('signedIn');
  }, [setUser]);

  const signUp = useCallback(async (b: { email: string; password: string; first_name: string; last_name?: string }) => {
    const s = await api.register({ ...b, email: b.email.trim(), timezone: deviceTimeZone() });
    await saveTokens(s);
    setUser(s.user);
    setStatus('signedIn');
  }, [setUser]);

  const signOut = useCallback(async () => {
    await api.logout();
    await forgetSession();
  }, [forgetSession]);

  const reloadUser = useCallback(async () => {
    setUser(await api.me());
  }, [setUser]);

  const value = useMemo(
    () => ({ status, user, signIn, signUp, signOut, setUser, reloadUser }),
    [status, user, signIn, signUp, signOut, setUser, reloadUser],
  );
  return <AuthContext value={value}>{children}</AuthContext>;
}

export function useAuth(): AuthValue {
  const ctx = use(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
