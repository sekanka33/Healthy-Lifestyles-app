import { router } from 'expo-router';
import { useState } from 'react';
import { Alert, Linking, StyleSheet, View } from 'react-native';

import { Button } from '@/components/ui/button';
import { FormScreen } from '@/components/ui/screen';
import { AppText } from '@/components/ui/text';
import { TextField } from '@/components/ui/text-field';
import { api, ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { manageSubscription } from '@/lib/purchases';
import { colors, radius } from '@/theme/tokens';

const PRIVACY_URL = process.env.EXPO_PUBLIC_PRIVACY_URL;

export default function Privacy() {
  const { user, signOut } = useAuth();
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);
  const [busy, setBusy] = useState<'export' | 'delete' | null>(null);

  async function exportData() {
    setBusy('export');
    setMessage(null);
    try {
      const r = await api.exportByEmail();
      setMessage({ text: `We're emailing a copy of your data to ${r.to}.` });
    } catch (e) {
      setMessage({ text: e instanceof ApiError ? e.userMessage : 'Could not start the export.', error: true });
    } finally {
      setBusy(null);
    }
  }

  function confirmDelete() {
    if (!password) return setMessage({ text: 'Enter your password to confirm.', error: true });
    Alert.alert('Delete your account?', 'This permanently deletes your account and all your data. It can’t be undone.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete forever', style: 'destructive', onPress: () => void doDelete() },
    ]);
  }

  async function doDelete() {
    setBusy('delete');
    setMessage(null);
    try {
      await api.deleteAccount(password);
      const wasPremium = user?.plan === 'premium';
      await signOut(); // tokens are already dead server-side; this clears the device
      if (wasPremium) {
        Alert.alert('Account deleted', 'Remember to cancel Premium in your App Store / Google Play account — the store bills you.',
          [{ text: 'Manage subscription', onPress: () => void manageSubscription() }, { text: 'OK' }]);
      }
    } catch (e) {
      setMessage({ text: e instanceof ApiError ? e.userMessage : 'Could not delete the account.', error: true });
      setBusy(null);
    }
  }

  return (
    <FormScreen>
      <AppText variant="title">Privacy & data</AppText>
      <AppText variant="caption">
        Your health data is used only to run the app for you. We don&apos;t sell it or use it for advertising. Locations are
        stored to about 1 km, calendars are read as free/busy only, and medication emails hide names unless you choose otherwise.
      </AppText>
      {PRIVACY_URL && <Button title="Read the privacy policy" variant="ghost" onPress={() => Linking.openURL(PRIVACY_URL)} />}

      <View style={styles.card}>
        <AppText variant="heading">Get a copy of your data</AppText>
        <AppText variant="caption">Everything we hold for your account, as a file emailed to {user?.email}.</AppText>
        <Button title="Email me my data" variant="secondary" onPress={exportData} loading={busy === 'export'} disabled={busy !== null} />
      </View>

      <View style={[styles.card, styles.danger]}>
        <AppText variant="heading">Delete account</AppText>
        <AppText variant="caption">
          Deletes your account, water, workouts, routes, medications, plans and calendar connection. A Premium subscription
          must also be cancelled in your App Store or Google Play account.
        </AppText>
        <TextField label="Password" value={password} onChangeText={setPassword} secureTextEntry autoComplete="current-password" />
        <Button title="Delete my account" variant="ghost" onPress={confirmDelete} loading={busy === 'delete'} disabled={busy !== null} />
      </View>

      {message && <AppText variant={message.error ? 'error' : 'caption'}>{message.text}</AppText>}
      <Button title="Done" variant="ghost" onPress={() => router.back()} />
    </FormScreen>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.accentWash, borderRadius: radius.md, padding: 16, gap: 10 },
  danger: { backgroundColor: '#FDF1F1' },
});
