import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { Button } from '@/components/ui/button';
import { FormScreen } from '@/components/ui/screen';
import { AppText } from '@/components/ui/text';
import { TextField } from '@/components/ui/text-field';
import { api, ApiError, GoalProgress } from '@/lib/api';
import { colors, fonts, radius } from '@/theme/tokens';

const PRESETS: { metric: GoalProgress['metric']; target: number; label: string }[] = [
  { metric: 'distance_km', target: 10, label: '10 km a week' },
  { metric: 'distance_km', target: 20, label: '20 km a week' },
  { metric: 'workout_count', target: 3, label: '3 workouts a week' },
  { metric: 'active_minutes', target: 150, label: '150 active minutes a week' },
];

function goalText(g: GoalProgress) {
  const unit = g.metric === 'distance_km' ? 'km' : g.metric === 'workout_count' ? 'workouts' : 'active minutes';
  return `${g.target_value} ${unit} ${g.period === 'weekly' ? 'a week' : 'a month'}`;
}

export default function FitnessSettings() {
  const [goals, setGoals] = useState<GoalProgress[]>([]);
  const [weight, setWeight] = useState('');
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);
  const [busy, setBusy] = useState(false);

  const fetchSettings = () => Promise.all([api.fitnessSummary('weekly'), api.fitnessProfile()]);

  function apply([s, p]: Awaited<ReturnType<typeof fetchSettings>>) {
    setGoals(s.goals);
    setWeight(p.body_weight_kg != null ? String(p.body_weight_kg) : '');
  }

  async function refresh() {
    apply(await fetchSettings());
  }

  useEffect(() => {
    Promise.all([api.fitnessSummary('weekly'), api.fitnessProfile()])
      .then(([s, p]) => {
        setGoals(s.goals);
        setWeight(p.body_weight_kg != null ? String(p.body_weight_kg) : '');
      })
      .catch(() => setMessage({ text: 'Could not load your goals.', error: true }));
  }, []);

  async function run(fn: () => Promise<unknown>, ok: string) {
    setBusy(true);
    setMessage(null);
    try {
      await fn();
      await refresh();
      setMessage({ text: ok });
    } catch (e) {
      setMessage({ text: e instanceof ApiError ? e.userMessage : 'Could not save.', error: true });
    } finally {
      setBusy(false);
    }
  }

  function saveWeight() {
    const kg = weight.trim() ? Number(weight.replace(',', '.')) : null;
    if (kg !== null && !(kg >= 20 && kg <= 400)) return setMessage({ text: 'Enter a weight between 20 and 400 kg.', error: true });
    void run(() => api.setFitnessProfile(kg), kg === null ? 'Weight removed.' : 'Weight saved.');
  }

  return (
    <FormScreen>
      <AppText variant="title">Goals & settings</AppText>

      <AppText variant="heading">Weekly goals</AppText>
      {goals.length === 0 && <AppText variant="caption">No goals yet. Pick one below.</AppText>}
      {goals.map((g) => (
        <View key={g.id} style={styles.row}>
          <AppText style={styles.flex}>{goalText(g)}</AppText>
          <Button title="Remove" variant="ghost" disabled={busy} onPress={() => run(() => api.removeFitnessGoal(g.id), 'Goal removed.')} />
        </View>
      ))}
      <View style={styles.wrap}>
        {PRESETS.filter((p) => !goals.some((g) => g.metric === p.metric && g.target_value === p.target)).map((p) => (
          <Pressable key={p.label} accessibilityRole="button" disabled={busy}
            onPress={() => run(() => api.addFitnessGoal({ metric: p.metric, period: 'weekly', target_value: p.target }), 'Goal added.')}
            style={styles.chip}>
            <AppText style={styles.chipText}>+ {p.label}</AppText>
          </Pressable>
        ))}
      </View>

      <AppText variant="heading" style={styles.gapTop}>Calorie estimates</AppText>
      <AppText variant="caption">
        Optional. Your weight is only used to estimate calories (activity × time × weight). Leave it empty and we
        won&apos;t show calories.
      </AppText>
      <TextField label="Body weight (kg)" value={weight} onChangeText={setWeight} keyboardType="decimal-pad" />
      <Button title="Save weight" variant="secondary" onPress={saveWeight} disabled={busy} />

      {message && <AppText variant={message.error ? 'error' : 'caption'}>{message.text}</AppText>}
      <Button title="Done" variant="ghost" onPress={() => router.back()} />
    </FormScreen>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', borderBottomWidth: 1, borderBottomColor: colors.border },
  flex: { flex: 1 },
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { minHeight: 40, paddingHorizontal: 14, borderRadius: radius.pill, backgroundColor: colors.chip, justifyContent: 'center' },
  chipText: { fontFamily: fonts.bold },
  gapTop: { marginTop: 12 },
});
