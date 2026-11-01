import { router } from 'expo-router';
import { useCallback } from 'react';

import { useAuth } from '@/lib/auth-context';

/**
 * Guest mode: visitors can browse every tab, but any action outside the tab bar needs an account.
 * `gate(fn)` returns a handler that runs `fn` for signed-in users and opens sign-in for guests.
 */
export function useAccountGate() {
  const { status } = useAuth();
  const isGuest = status !== 'signedIn';

  const gate = useCallback(
    <A extends unknown[]>(fn: (...args: A) => unknown) =>
      (...args: A) => {
        if (isGuest) router.push('/sign-in');
        else fn(...args);
      },
    [isGuest],
  );

  return { isGuest, gate };
}
