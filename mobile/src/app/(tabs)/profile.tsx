import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { FeatureTable } from '@/components/feature-table';
import { Button } from '@/components/ui/button';
import { AppText } from '@/components/ui/text';
import { TextField } from '@/components/ui/text-field';
import { useAccountGate } from '@/hooks/use-account-gate';
import { api, ApiError } from '@/lib/api';
import { deviceTimeZone, useAuth } from '@/lib/auth-context';
import { sync, useHydration } from '@/lib/hydration-store';
import { colors, fonts, radius } from '@/theme/tokens';

const GOAL_PRESETS = [1500, 2000, 2500, 3000];

export default function Profile() {
  const { status, user } = useAuth();
  // Guests must never trigger account API calls (they'd just bounce off 401s).
  return status === 'signedIn' && user ? <SignedInProfile /> : <GuestProfile />;
}

/** What a visitor can explore without an account. Every button leads to sign-in. */
function GuestProfile() {
  const { gate } = useAccountGate();
  const settings = [
    { title: 'Daily water goal', detail: 'Pick 1.5–3 L or any custom amount. Past days keep their goal.' },
    { title: 'Reminders', detail: 'Gentle hydration nudges with quiet hours.' },
    { title: 'Units & time zone', detail: 'Metric or imperial; your day resets at local midnight.' },
    { title: 'Premium', detail: 'Medication reminders, GPS workouts, weather-aware plans.' },
    { title: 'Payment history', detail: 'Every payment you make, in one place.' },
  ];
  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView contentContainerStyle={styles.content}>
        <AppText variant="title">Profile</AppText>
        <View style={styles.guestCard}>
          <AppText variant="heading">You&apos;re browsing as a guest</AppText>
          <AppText variant="caption">
            Look around as much as you like. To track water, set goals or use any feature, sign in or create a free account.
          </AppText>
          <Button title="SIGN IN OR CREATE ACCOUNT" onPress={gate(() => undefined)} />
        </View>

        <Section title="What you can do">
          <FeatureTable />
        </Section>

        <Section title="Your settings">
          {settings.map((item) => (
            <Pressable key={item.title} accessibilityRole="button" accessibilityHint="Opens sign in"
              onPress={gate(() => undefined)} style={({ pressed }) => [styles.settingRow, pressed && styles.pressed]}>
              <View style={styles.flex}>
                <AppText style={styles.settingTitle}>{item.title}</AppText>
                <AppText variant="caption">{item.detail}</AppText>
              </View>
              <AppText style={styles.chevron}>›</AppText>
            </Pressable>
          ))}
        </Section>
      </ScrollView>
    </SafeAreaView>
  );
}

function SignedInProfile() {
  const { user, setUser, signOut } = useAuth();
  const { pendingCount } = useHydration();
  const [firstName, setFirstName] = useState(user?.first_name ?? '');
  const [lastName, setLastName] = useState(user?.last_name ?? '');
  const [goal, setGoal] = useState<string>('');
  const [savedGoal, setSavedGoal] = useState<number | null>(null);
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);
  const [busy, setBusy] = useState(false);

  useFocusEffect(useCallback(() => {
    api.goal().then((g) => {
      setSavedGoal(g.daily_goal_ml);
      setGoal(String(g.daily_goal_ml));
    }).catch(() => undefined);
  }, []));

  if (!user) return null;
  const deviceTz = deviceTimeZone();
  const dirtyName = firstName.trim() !== user.first_name || (lastName.trim() || null) !== user.last_name;
  const goalNum = Number(goal);
  const dirtyGoal = savedGoal !== null && goalNum !== savedGoal;

  async function save() {
    if (!firstName.trim()) return setMessage({ text: 'First name is required.', error: true });
    if (dirtyGoal && (!Number.isInteger(goalNum) || goalNum < 250 || goalNum > 10000)) {
      return setMessage({ text: 'Daily goal must be between 250 and 10,000 ml.', error: true });
    }
    setBusy(true);
    setMessage(null);
    try {
      if (dirtyName) setUser(await api.updateMe({ first_name: firstName.trim(), last_name: lastName.trim() || null }));
      if (dirtyGoal) {
        setSavedGoal((await api.setGoal(goalNum)).daily_goal_ml);
        void sync();
      }
      setMessage({ text: 'Saved.' });
    } catch (e) {
      setMessage({ text: e instanceof ApiError ? e.userMessage : 'Could not save.', error: true });
    } finally {
      setBusy(false);
    }
  }

  async function patch(b: Parameters<typeof api.updateMe>[0]) {
    try {
      setUser(await api.updateMe(b));
      void sync();
    } catch (e) {
      setMessage({ text: e instanceof ApiError ? e.userMessage : 'Could not save.', error: true });
    }
  }

  function confirmSignOut() {
    const warn = pendingCount > 0
      ? `You have ${pendingCount} unsynced change(s). Signing out now will discard them.`
      : 'You can sign back in any time.';
    Alert.alert('Sign out?', warn, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Sign out', style: 'destructive', onPress: () => void signOut() },
    ]);
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <AppText variant="title">Profile</AppText>
        <View style={styles.planRow}>
          <AppText variant="caption">{user.email}</AppText>
          <View style={styles.plan}><AppText style={styles.planText}>{user.plan === 'premium' ? 'Premium' : 'Free plan'}</AppText></View>
        </View>

        <Section title="Your plan">
          {user.plan === 'premium' ? (
            <>
              <AppText variant="caption">You have Premium. Thank you!</AppText>
              <Button title="Subscription details" variant="secondary" onPress={() => router.push('/premium')} />
            </>
          ) : (
            <>
              <AppText variant="caption">Unlock medication reminders, GPS workouts and weather-aware plans.</AppText>
              <Button title="Upgrade to Premium" onPress={() => router.push('/premium')} />
            </>
          )}
          <Button title="Payment history" variant="ghost" onPress={() => router.push('/payments')} />
        </Section>

        <Section title="About you">
          <TextField label="First name" value={firstName} onChangeText={setFirstName} autoComplete="given-name" />
          <TextField label="Last name" value={lastName} onChangeText={setLastName} autoComplete="family-name" />
        </Section>

        <Section title="Daily water goal">
          <View style={styles.presets}>
            {GOAL_PRESETS.map((p) => (
              <Pressable key={p} onPress={() => setGoal(String(p))} accessibilityRole="radio"
                accessibilityState={{ selected: goalNum === p }} style={[styles.preset, goalNum === p && styles.presetOn]}>
                <AppText style={styles.presetLabel}>{(p / 1000).toFixed(1)} L</AppText>
              </Pressable>
            ))}
          </View>
          <TextField label="Custom (ml)" value={goal} keyboardType="number-pad"
            onChangeText={(t) => setGoal(t.replace(/\D/g, '').slice(0, 5))}
            hint="A new goal applies from today. Past days keep the goal they had." />
        </Section>

        {(dirtyName || dirtyGoal) && <Button title="SAVE CHANGES" onPress={save} loading={busy} />}
        {message && <AppText variant={message.error ? 'error' : 'caption'}>{message.text}</AppText>}

        <Section title="Units">
          <View style={styles.presets}>
            {(['metric', 'imperial'] as const).map((u) => (
              <Pressable key={u} onPress={() => patch({ units: u })} accessibilityRole="radio"
                accessibilityState={{ selected: user.units === u }} style={[styles.preset, user.units === u && styles.presetOn]}>
                <AppText style={styles.presetLabel}>{u === 'metric' ? 'Metric' : 'Imperial'}</AppText>
              </Pressable>
            ))}
          </View>
        </Section>

        <Section title="Time zone">
          <AppText>{user.timezone}</AppText>
          <AppText variant="caption">Your day resets at midnight in this time zone.</AppText>
          {deviceTz !== user.timezone && (
            <Button title={`Use device time zone (${deviceTz})`} variant="secondary" onPress={() => patch({ timezone: deviceTz })} />
          )}
        </Section>

        <Section title="Security">
          <Button title="Change password" variant="secondary" onPress={() => router.push('/change-password')} />
          <Button title="Sign out" variant="ghost" onPress={confirmSignOut} />
        </Section>
      </ScrollView>
    </SafeAreaView>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <AppText variant="heading">{title}</AppText>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  content: { padding: 24, gap: 18, paddingBottom: 48 },
  planRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' },
  plan: { backgroundColor: colors.accentSoft, borderRadius: radius.pill, paddingHorizontal: 12, paddingVertical: 4 },
  planText: { fontFamily: fonts.bold, color: colors.tabActive, fontSize: 13 },
  section: { gap: 10, paddingTop: 8 },
  presets: { flexDirection: 'row', gap: 10, flexWrap: 'wrap' },
  preset: { paddingHorizontal: 16, height: 40, borderRadius: radius.pill, backgroundColor: colors.chip, justifyContent: 'center' },
  presetOn: { backgroundColor: colors.chipSelected, borderWidth: 2, borderColor: colors.primary },
  presetLabel: { fontFamily: fonts.bold },
  guestCard: { backgroundColor: colors.accentWash, borderRadius: radius.md, padding: 16, gap: 10 },
  settingRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: colors.border },
  settingTitle: { fontFamily: fonts.bold },
  chevron: { fontFamily: fonts.heavy, fontSize: 22, color: colors.textMuted },
  flex: { flex: 1, gap: 2 },
  pressed: { opacity: 0.6 },
});
