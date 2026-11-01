import { router } from 'expo-router';
import { useCallback } from 'react';

import { useAuth } from '@/lib/auth-context';

/**
 * Browsing is open to everyone; acting needs a verified account.
 * `isGuest` is true for visitors without an account AND for accounts whose email isn't verified yet:
 * both see the sample content. `gate(fn)` runs `fn` for verified users, otherwise opens
 * Login/Register (no account) or the verify-email screen (unverified account).
 */
export function useAccountGate() {
  const { status, user } = useAuth();
  const signedIn = status === 'signedIn';
  const isGuest = !signedIn || !user?.email_verified;

  const gate = useCallback(
    <A extends unknown[]>(fn: (...args: A) => unknown) =>
      (...args: A) => {
        if (!signedIn) router.push('/sign-in');
        else if (isGuest) router.push('/verify-email');
        else fn(...args);
      },
    [signedIn, isGuest],
  );

  return { isGuest, needsVerification: signedIn && isGuest, gate };
}
