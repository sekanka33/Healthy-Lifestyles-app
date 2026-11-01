import * as Crypto from 'expo-crypto';
import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { Button } from '@/components/ui/button';
import { FormScreen } from '@/components/ui/screen';
import { AppText } from '@/components/ui/text';
import { TextField } from '@/components/ui/text-field';
import { Activity, api, ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { colors, fonts, radius } from '@/theme/tokens';

const ACTIVITIES: { value: Activity; label: string }[] = [
  { value: 'walking', label: 'Walk' }, { value: 'jogging', label: 'Jog' }, { value: 'running', label: 'Run' },
];

export default function ManualWorkout() {
  const { user } = useAuth();
  const imperial = user?.units === 'imperial';
  const [activity, setActivity] = useState<Activity>('walking');
  const [distance, setDistance] = useState('');
  const [minutes, setMinutes] = useState('');
  const [hoursAgo, setHoursAgo] = useState('1');
  const [clientId] = useState(() => Crypto.randomUUID()); // retrying the same form never doubles it
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    const d = Number(distance.replace(',', '.'));
    const m = Number(minutes);
    const ago = Number(hoursAgo);
    if (!(d >= 0 && d <= 300)) return setError('Enter a distance between 0 and 300.');
    if (!(Number.isInteger(m) && m >= 1 && m <= 1440)) return setError('Enter the duration in whole minutes.');
    if (!(ago >= 0 && ago <= 24 * 30)) return setError('Enter how many hours ago you started (up to 30 days).');
    const startedAt = new Date(Date.now() - ago * 3600_000);
    if (startedAt.getTime() + m * 60_000 > Date.now() + 60_000) return setError('That workout would end in the future.');
    setBusy(true);
    setError(null);
    try {
      await api.manualWorkout({ client_id: clientId, activity_type: activity, started_at: startedAt.toISOString(),
        active_duration_s: m * 60, distance_m: d * (imperial ? 1609.344 : 1000) });
      router.back();
    } catch (e) {
      setError(e instanceof ApiError ? e.userMessage : 'Could not save.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <FormScreen>
      <AppText variant="title">Log a workout</AppText>
      <View style={styles.wrap} accessibilityRole="radiogroup">
        {ACTIVITIES.map((a) => (
          <Pressable key={a.value} accessibilityRole="radio" accessibilityState={{ selected: activity === a.value }}
            onPress={() => setActivity(a.value)} style={[styles.chip, activity === a.value && styles.chipOn]}>
            <AppText style={styles.chipText}>{a.label}</AppText>
          </Pressable>
        ))}
      </View>
      <TextField label={`Distance (${imperial ? 'miles' : 'km'})`} value={distance} onChangeText={setDistance} keyboardType="decimal-pad" />
      <TextField label="Duration (minutes)" value={minutes} onChangeText={(t) => setMinutes(t.replace(/\D/g, '').slice(0, 4))} keyboardType="number-pad" />
      <TextField label="Started how many hours ago?" value={hoursAgo} onChangeText={(t) => setHoursAgo(t.replace(/[^\d.]/g, '').slice(0, 5))}
        keyboardType="decimal-pad" hint="0 = just now" />
      {error && <AppText variant="error">{error}</AppText>}
      <Button title="SAVE WORKOUT" onPress={save} loading={busy} />
      <Button title="Cancel" variant="ghost" onPress={() => router.back()} />
    </FormScreen>
  );
}

const styles = StyleSheet.create({
  wrap: { flexDirection: 'row', gap: 8 },
  chip: { minHeight: 40, paddingHorizontal: 18, borderRadius: radius.pill, backgroundColor: colors.chip, justifyContent: 'center' },
  chipOn: { backgroundColor: colors.chipSelected, borderWidth: 2, borderColor: colors.primary },
  chipText: { fontFamily: fonts.bold },
});
