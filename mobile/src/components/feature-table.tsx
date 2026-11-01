import { StyleSheet, View } from 'react-native';

import { AppText } from '@/components/ui/text';
import { colors, fonts, radius } from '@/theme/tokens';

export const FEATURES: { label: string; free: boolean }[] = [
  { label: 'Water tracking, goals, history & reports', free: true },
  { label: 'Current weather', free: true },
  { label: 'Google Calendar free-time view', free: true },
  { label: 'Medication schedules & reminders', free: false },
  { label: 'GPS walks, runs & health app sync', free: false },
  { label: 'Weather-aware exercise suggestions', free: false },
  { label: 'Add planned activities to your calendar', free: false },
];

/** Read-only Free vs Premium comparison (paywall and guest profile). */
export function FeatureTable() {
  return (
    <View style={styles.table} accessibilityLabel="What's included">
      <View style={styles.row}>
        <AppText variant="label" style={styles.flex}>Feature</AppText>
        <AppText variant="label" style={styles.col}>Free</AppText>
        <AppText variant="label" style={styles.col}>Premium</AppText>
      </View>
      {FEATURES.map((f) => (
        <View key={f.label} style={styles.row} accessible
          accessibilityLabel={`${f.label}: ${f.free ? 'included in Free and Premium' : 'Premium only'}`}>
          <AppText style={styles.flex}>{f.label}</AppText>
          <AppText style={[styles.col, f.free ? styles.yes : styles.no]}>{f.free ? '✓' : '—'}</AppText>
          <AppText style={[styles.col, styles.yes]}>✓</AppText>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  table: { backgroundColor: colors.accentWash, borderRadius: radius.md, padding: 16, gap: 10 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  flex: { flex: 1 },
  col: { width: 64, textAlign: 'center' },
  yes: { color: colors.tabActive, fontFamily: fonts.heavy },
  no: { color: colors.textMuted },
});
