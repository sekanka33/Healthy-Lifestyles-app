import { Pressable, ScrollView, StyleSheet, View } from 'react-native';

import { Button } from '@/components/ui/button';
import { AppText } from '@/components/ui/text';
import type { WeatherState } from '@/hooks/use-weather';
import type { CurrentWeather, Forecast } from '@/lib/api';
import { capitalise, conditionGlyph, formatTemp, formatWind, outdoorVerdict } from '@/lib/weather-format';
import { colors, fonts, radius } from '@/theme/tokens';

type Units = 'metric' | 'imperial';

const LABEL_COLOR = { good: colors.tabActive, fair: colors.navySoft, poor: colors.danger } as const;

function hour(iso: string) {
  return new Date(iso).toLocaleTimeString(undefined, { hour: 'numeric' });
}

/** Full card: current conditions, outdoor verdict, optional forecast strip. */
export function WeatherCard({ state, units, onChooseLocation, onRetry, sample }: {
  state: WeatherState;
  units: Units;
  onChooseLocation: () => void;
  onRetry: () => void;
  sample?: { current: CurrentWeather; forecast: Forecast | null };
}) {
  const data = sample ?? (state.status === 'ready' ? state : null);
  if (!data) {
    return (
      <View style={styles.card}>
        {state.status === 'no_location' ? (
          <>
            <AppText variant="heading">Weather</AppText>
            <AppText variant="caption">Choose a location to see the weather and whether it&apos;s a good time to get outside.</AppText>
            <Button title="Choose location" variant="secondary" onPress={onChooseLocation} />
          </>
        ) : state.status === 'error' ? (
          <>
            <AppText variant="caption">{state.message}</AppText>
            <Button title="Try again" variant="ghost" onPress={onRetry} />
          </>
        ) : (
          <AppText variant="caption">Loading weather…</AppText>
        )}
      </View>
    );
  }

  const { current: c, forecast: f } = data;
  return (
    <View style={styles.card} accessible={false}>
      <View style={styles.top}>
        <AppText style={styles.glyph} accessibilityElementsHidden>{conditionGlyph(c.condition.code, c.is_day)}</AppText>
        <View style={styles.flex} accessible accessibilityLabel={`${formatTemp(c.temp_c, units)}, ${c.condition.description}`}>
          <AppText style={styles.temp}>{formatTemp(c.temp_c, units)}</AppText>
          <AppText variant="caption">{capitalise(c.condition.description)} · feels {formatTemp(c.feels_like_c, units)}</AppText>
        </View>
        <Pressable accessibilityRole="button" accessibilityLabel="Change weather location" onPress={onChooseLocation}>
          <AppText style={styles.place} numberOfLines={1}>{c.place_name ?? 'Your area'} ›</AppText>
        </Pressable>
      </View>
      <AppText style={[styles.verdict, { color: LABEL_COLOR[c.outdoor.label] }]}>{outdoorVerdict(c.outdoor.label)}</AppText>
      <AppText variant="caption">{c.outdoor.reasons.join(' · ')} · wind {formatWind(c.wind_mps, units)}</AppText>
      {c.hydration_tip && <AppText variant="caption" style={styles.tip}>💧 {c.hydration_tip}</AppText>}

      {f && f.steps.length > 0 && (
        <>
          {f.best_time && (
            <AppText style={styles.best}>Best time to get outside: {hour(f.best_time)}</AppText>
          )}
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.strip}>
            {f.steps.map((s) => (
              <View key={s.at} style={[styles.step, s.at === f.best_time && styles.stepBest]}
                accessible accessibilityLabel={`${hour(s.at)}: ${formatTemp(s.temp_c, units)}, ${s.outdoor.label} for exercise`}>
                <AppText style={styles.stepHour}>{hour(s.at)}</AppText>
                <AppText style={styles.stepGlyph}>{conditionGlyph(s.condition.code, s.is_day)}</AppText>
                <AppText style={styles.stepTemp}>{formatTemp(s.temp_c, units)}</AppText>
                <View style={[styles.dot, { backgroundColor: LABEL_COLOR[s.outdoor.label] }]} />
              </View>
            ))}
          </ScrollView>
        </>
      )}
      {(c.stale || f?.stale) && <AppText variant="caption">Showing the latest available data.</AppText>}
      {sample && <AppText style={styles.sample}>Sample</AppText>}
    </View>
  );
}

/** One-line chip for the Water screen header. */
export function WeatherChip({ state, units, onPress }: { state: WeatherState; units: Units; onPress: () => void }) {
  const text = state.status === 'ready'
    ? `${conditionGlyph(state.current.condition.code, state.current.is_day)} ${formatTemp(state.current.temp_c, units)}`
    : state.status === 'no_location' ? '☁️ Set weather' : null;
  if (!text) return null;
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={state.status === 'ready' ? `Weather ${text}` : 'Set weather location'}
      onPress={onPress} style={styles.chip}>
      <AppText style={styles.chipText}>{text}</AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.accentWash, borderRadius: radius.md, padding: 16, gap: 8 },
  top: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  flex: { flex: 1 },
  glyph: { fontSize: 36, lineHeight: 44 },
  temp: { fontFamily: fonts.heavy, fontSize: 28, lineHeight: 34 },
  place: { fontFamily: fonts.bold, color: colors.tabActive, maxWidth: 140 },
  verdict: { fontFamily: fonts.bold, fontSize: 16 },
  tip: { color: colors.navy },
  best: { fontFamily: fonts.bold, marginTop: 4 },
  strip: { gap: 8, paddingVertical: 4 },
  step: { alignItems: 'center', paddingVertical: 8, paddingHorizontal: 10, borderRadius: radius.sm, backgroundColor: colors.surface, gap: 2 },
  stepBest: { borderWidth: 2, borderColor: colors.primary },
  stepHour: { fontSize: 12, color: colors.navySoft },
  stepGlyph: { fontSize: 18 },
  stepTemp: { fontFamily: fonts.bold, fontSize: 14 },
  dot: { width: 8, height: 8, borderRadius: 4, marginTop: 2 },
  sample: { alignSelf: 'flex-start', fontFamily: fonts.bold, fontSize: 12, color: colors.tabActive },
  chip: { backgroundColor: colors.accentWash, borderRadius: radius.pill, paddingHorizontal: 12, paddingVertical: 4 },
  chipText: { fontFamily: fonts.bold, fontSize: 14 },
});
