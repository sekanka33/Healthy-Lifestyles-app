import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/button';
import { AppText } from '@/components/ui/text';
import { api, ApiError, DaySummary } from '@/lib/api';
import { colors, fonts, radius } from '@/theme/tokens';

const RANGES = [7, 30] as const;

function weekday(date: string) {
  // Parse as a calendar date (not an instant) so the label can't shift across time zones.
  const [y, m, d] = date.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(undefined, { weekday: 'short', timeZone: 'UTC' });
}

function shortDate(date: string) {
  const [y, m, d] = date.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(undefined, { day: 'numeric', month: 'short', timeZone: 'UTC' });
}

export default function History() {
  const [range, setRange] = useState<(typeof RANGES)[number]>(7);
  const [days, setDays] = useState<DaySummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (r: number) => {
    setError(null);
    try {
      const all = (await api.history()).days; // default window: last 7 days ending today
      if (r === 7) return setDays(all);
      const to = all[all.length - 1].date;
      const [y, m, d] = to.split('-').map(Number);
      const from = new Date(Date.UTC(y, m - 1, d - (r - 1))).toISOString().slice(0, 10);
      setDays((await api.history(from, to)).days);
    } catch (e) {
      setError(e instanceof ApiError ? e.userMessage : 'Could not load history.');
    }
  }, []);

  useFocusEffect(useCallback(() => void load(range), [load, range]));

  const max = Math.max(...(days ?? []).map((d) => Math.max(d.total_ml, d.goal_ml)), 1);
  const met = (days ?? []).filter((d) => d.goal_met).length;
  const avg = days?.length ? Math.round(days.reduce((s, d) => s + d.total_ml, 0) / days.length) : 0;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => {
          setRefreshing(true);
          await load(range);
          setRefreshing(false);
        }} />}>
        <AppText variant="title">History</AppText>
        <View style={styles.segment} accessibilityRole="tablist">
          {RANGES.map((r) => (
            <Pressable key={r} accessibilityRole="tab" accessibilityState={{ selected: range === r }}
              onPress={() => { setRange(r); setDays(null); }} style={[styles.segItem, range === r && styles.segOn]}>
              <AppText style={[styles.segLabel, range === r && styles.segLabelOn]}>{r} days</AppText>
            </Pressable>
          ))}
        </View>

        {error ? (
          <View style={styles.empty}>
            <AppText variant="error">{error}</AppText>
            <Button title="Try again" variant="secondary" onPress={() => load(range)} />
          </View>
        ) : !days ? (
          <ActivityIndicator color={colors.primary} style={{ marginTop: 40 }} />
        ) : (
          <>
            <View style={styles.stats}>
              <Stat label="Daily average" value={`${avg.toLocaleString()} ml`} />
              <Stat label="Goal met" value={`${met} / ${days.length} days`} />
            </View>

            {range === 7 && (
              <View style={styles.chart} accessibilityLabel="Daily intake chart">
                {days.map((d) => (
                  <View key={d.date} style={styles.barCol}>
                    <View style={styles.barTrack}>
                      <View style={[styles.goalLine, { bottom: `${(d.goal_ml / max) * 100}%` }]} />
                      <View style={[styles.bar, { height: `${(d.total_ml / max) * 100}%` },
                        d.goal_met && { backgroundColor: colors.primary }]} />
                    </View>
                    <AppText style={styles.barLabel}>{weekday(d.date)}</AppText>
                  </View>
                ))}
              </View>
            )}

            <View style={styles.list}>
              {[...days].reverse().map((d) => (
                <View key={d.date} style={styles.row}
                  accessibilityLabel={`${shortDate(d.date)}: ${d.total_ml} of ${d.goal_ml} millilitres${d.goal_met ? ', goal met' : ''}`}>
                  <AppText style={styles.rowDate}>{weekday(d.date)} {shortDate(d.date)}</AppText>
                  <AppText style={styles.rowValue}>
                    {d.total_ml.toLocaleString()} / {d.goal_ml.toLocaleString()} ml {d.goal_met ? '✓' : ''}
                  </AppText>
                </View>
              ))}
            </View>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.stat}>
      <AppText variant="label">{label}</AppText>
      <AppText style={styles.statValue}>{value}</AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  content: { padding: 24, gap: 18, paddingBottom: 40 },
  segment: { flexDirection: 'row', backgroundColor: colors.chip, borderRadius: radius.pill, padding: 4, alignSelf: 'flex-start' },
  segItem: { paddingHorizontal: 18, paddingVertical: 8, borderRadius: radius.pill },
  segOn: { backgroundColor: colors.surface },
  segLabel: { fontFamily: fonts.bold, color: colors.navySoft },
  segLabelOn: { color: colors.tabActive },
  stats: { flexDirection: 'row', gap: 12 },
  stat: { flex: 1, backgroundColor: colors.accentWash, borderRadius: radius.md, padding: 16, gap: 4 },
  statValue: { fontFamily: fonts.heavy, fontSize: 20 },
  chart: { flexDirection: 'row', height: 180, gap: 10, alignItems: 'flex-end' },
  barCol: { flex: 1, alignItems: 'center', gap: 6, height: '100%' },
  barTrack: { flex: 1, width: '100%', justifyContent: 'flex-end', backgroundColor: colors.glassBody, borderRadius: 10, overflow: 'hidden' },
  bar: { width: '100%', backgroundColor: colors.waterBubble, opacity: 0.85, borderRadius: 10 },
  goalLine: { position: 'absolute', left: 0, right: 0, height: 2, backgroundColor: colors.navySoft, opacity: 0.35 },
  barLabel: { fontSize: 12, color: colors.navySoft },
  list: { gap: 2 },
  row: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: colors.border },
  rowDate: { fontFamily: fonts.bold },
  rowValue: { color: colors.navySoft },
  empty: { gap: 12, marginTop: 24 },
});
