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
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AuthProvider, useAuth } from '@/lib/auth-context';
import { isMedicationReminder } from '@/lib/medication-reminders';
import '@/lib/workout-tracker'; // registers the background location task at startup
import { colors } from '@/theme/tokens';

SplashScreen.preventAutoHideAsync();

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

  // Tapping a medication reminder opens the Meds tab (guests are routed to sign-in by the guard).
  useEffect(() => {
    const sub = Notifications.addNotificationResponseReceivedListener((response) => {
      if (isMedicationReminder(response)) router.navigate('/medications');
    });
    return () => sub.remove();
  }, []);

  const signedIn = status === 'signedIn';
  const verified = !!user?.email_verified;

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
