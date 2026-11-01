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
import { useEffect } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AuthProvider, useAuth } from '@/lib/auth-context';
import { isMedicationReminder } from '@/lib/medication-reminders';
import { colors } from '@/theme/tokens';

SplashScreen.preventAutoHideAsync();

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

  if (status === 'loading') return null;
  const signedIn = status === 'signedIn';
  const verified = !!user?.email_verified;

  return (
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.background } }}>
      {/* Guests browse the tabs freely; any action inside them opens Login/Register (no way back without signing in). */}
      <Stack.Protected guard={!signedIn || verified}>
        <Stack.Screen name="(tabs)" />
      </Stack.Protected>
      <Stack.Protected guard={signedIn && verified}>
        <Stack.Screen name="change-password" options={{ presentation: 'modal' }} />
        <Stack.Screen name="premium" options={{ presentation: 'modal' }} />
        <Stack.Screen name="payments" options={{ presentation: 'modal' }} />
        <Stack.Screen name="medication-edit" options={{ presentation: 'modal' }} />
      </Stack.Protected>
      <Stack.Protected guard={signedIn && !verified}>
        <Stack.Screen name="verify-email" />
      </Stack.Protected>
      <Stack.Protected guard={!signedIn}>
        {/* Full screen, not a dismissable sheet: the only way forward is to sign in or register. */}
        <Stack.Screen name="(auth)" options={{ gestureEnabled: false, animation: 'slide_from_bottom' }} />
      </Stack.Protected>
    </Stack>
  );
}
