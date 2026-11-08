import {
  Nunito_600SemiBold,
  Nunito_700Bold,
  Nunito_800ExtraBold,
  useFonts,
} from '@expo-google-fonts/nunito';
import * as Notifications from 'expo-notifications';
import { router, Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useRef } from 'react';
import { AppState, Platform } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AuthProvider, useAuth } from '@/lib/auth-context';
import { isHydrationReminder, syncHydrationReminders } from '@/lib/hydration-reminders';
import { hydrationGoalMet } from '@/lib/hydration-store';
import { isMedicationReminder, syncMedicationReminders } from '@/lib/medication-reminders';
import '@/lib/workout-tracker'; // registers the background location task at startup
import { colors } from '@/theme/tokens';

SplashScreen.preventAutoHideAsync();

// Decides how a notification appears while the app is open.
Notifications.setNotificationHandler({
  handleNotification: async (notification) => {
    const show = !(isHydrationReminder(notification) && hydrationGoalMet()); // no water nudge once the goal is met
    return { shouldShowBanner: show, shouldShowList: show, shouldPlaySound: show, shouldSetBadge: false };
  },
});

/** Tapping a reminder opens the screen it's about (guests are routed to sign-in by the guard). */
function openReminder(response: Notifications.NotificationResponse) {
  if (isMedicationReminder(response)) router.navigate('/medications');
  // dismissTo closes anything open on top of the tabs (a settings sheet, say) rather than stacking.
  else if (isHydrationReminder(response.notification)) router.dismissTo('/');
}

// Whatever the auth state, the first screen anyone sees is the app's content (the tabs).
export const unstable_settings = { initialRouteName: '(tabs)' };

export default function RootLayout() {
  const [fontsLoaded, fontError] = useFonts({ Nunito_600SemiBold, Nunito_700Bold, Nunito_800ExtraBold });
  if (!fontsLoaded && !fontError) return null;
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <StatusBar style="dark" />
        <RootNavigator />
      </AuthProvider>
    </SafeAreaProvider>
  );
}

function RootNavigator() {
  const { status, user } = useAuth();

  useEffect(() => {
    if (status !== 'loading') SplashScreen.hideAsync();
  }, [status]);

  // A tap while the app is running.
  useEffect(() => {
    const sub = Notifications.addNotificationResponseReceivedListener(openReminder);
    return () => sub.remove();
  }, []);

  // A tap that launched the app: act once the navigator below is mounted. Cleared so that it isn't
  // replayed on the next launch.
  const ready = status !== 'loading';
  useEffect(() => {
    if (!ready || Platform.OS === 'web') return;
    Notifications.getLastNotificationResponseAsync().then((response) => {
      if (!response) return;
      void Notifications.clearLastNotificationResponseAsync();
      setTimeout(() => openReminder(response), 0);
    }).catch(() => undefined);
  }, [ready]);

  const signedIn = status === 'signedIn';
  const verified = !!user?.email_verified;

  // Keep this device's water reminders in step with the account, including changes made elsewhere.
  const account = signedIn && verified;
  // Medication reminders are scheduled a week ahead, so top them up on every foreground too —
  // not only when the Meds tab is opened — or they run dry for someone who never visits it.
  const medsTimeZone = account && user?.plan === 'premium' ? user.timezone : null;
  useEffect(() => {
    if (!account) return;
    const refresh = () => {
      void syncHydrationReminders().catch(() => undefined);
      if (medsTimeZone) void syncMedicationReminders(medsTimeZone).catch(() => undefined);
    };
    refresh();
    const sub = AppState.addEventListener('change', (s) => s === 'active' && refresh());
    return () => sub.remove();
  }, [account, medsTimeZone]);

  // Straight after registering (or signing in to an unverified account) go to the code screen.
  // On a cold start we don't: the app opens on its content and the gate sends them there on demand.
  const previous = useRef(status);
  useEffect(() => {
    const was = previous.current;
    previous.current = status;
    if (was === 'signedOut' && signedIn && !verified) setTimeout(() => router.push('/verify-email'), 0);
  }, [status, signedIn, verified]);

  if (status === 'loading') return null;

  return (
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.background } }}>
      {/* Everyone browses the tabs. Actions inside them need an account (Login/Register) and, for a new
          account, a verified email (verify screen). Neither screen has a way back to browsing. */}
      <Stack.Screen name="(tabs)" />
      <Stack.Protected guard={signedIn && verified}>
        <Stack.Screen name="change-password" options={{ presentation: 'modal' }} />
        <Stack.Screen name="premium" options={{ presentation: 'modal' }} />
        <Stack.Screen name="payments" options={{ presentation: 'modal' }} />
        <Stack.Screen name="medication-edit" options={{ presentation: 'modal' }} />
        <Stack.Screen name="workout/[id]" />
        <Stack.Screen name="workout-manual" options={{ presentation: 'modal' }} />
        <Stack.Screen name="fitness-settings" options={{ presentation: 'modal' }} />
        <Stack.Screen name="weather-location" options={{ presentation: 'modal' }} />
        <Stack.Screen name="plan" />
        <Stack.Screen name="plan-settings" options={{ presentation: 'modal' }} />
        <Stack.Screen name="email-settings" options={{ presentation: 'modal' }} />
        <Stack.Screen name="hydration-reminders" options={{ presentation: 'modal' }} />
        <Stack.Screen name="privacy" options={{ presentation: 'modal' }} />
      </Stack.Protected>
      <Stack.Protected guard={signedIn && !verified}>
        <Stack.Screen name="verify-email" options={{ gestureEnabled: false, animation: 'slide_from_bottom' }} />
      </Stack.Protected>
      <Stack.Protected guard={!signedIn}>
        {/* Full screen, not a dismissable sheet: the only way forward is to sign in or register. */}
        <Stack.Screen name="(auth)" options={{ gestureEnabled: false, animation: 'slide_from_bottom' }} />
      </Stack.Protected>
    </Stack>
  );
}
