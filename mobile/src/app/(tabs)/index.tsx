import * as Haptics from 'expo-haptics';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { AppState, Modal, Platform, Pressable, StyleSheet, useWindowDimensions, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { UndoIcon } from '@/components/icons';
import { Button } from '@/components/ui/button';
import { AppText } from '@/components/ui/text';
import { TextField } from '@/components/ui/text-field';
import { WaterGlass } from '@/components/water-glass';
import { WeatherChip } from '@/components/weather-card';
import { useAccountGate } from '@/hooks/use-account-gate';
import { useCountUp } from '@/hooks/use-count-up';
import { useWeather, WeatherState } from '@/hooks/use-weather';
import { useAuth } from '@/lib/auth-context';
import { addWater, initHydration, setHydrationTimeZone, sync, undoLast, useHydration } from '@/lib/hydration-store';
import { colors, fonts, radius } from '@/theme/tokens';

const CHIPS = [100, 250, 500];
const SAMPLE_WEATHER_CHIP: WeatherState = {
  status: 'ready',
  forecast: null,
  current: {
    lat: 0, lon: 0, place_name: null, observed_at: null, temp_c: 21, feels_like_c: 21, humidity: 45, wind_mps: 3,
    wind_gust_mps: null, rain_mm_1h: 0, condition: { code: 800, main: 'Clear', description: 'clear sky', icon: '01d' },
    sunrise: null, sunset: null, is_day: true, hydration_tip: null, stale: false,
    outdoor: { score: 100, label: 'good', reasons: [] },
  },
};
/** What guests see: a clearly labelled example, never real data. */
const SAMPLE = { totalMl: 1250, goalMl: 2000, entries: [{}], pendingCount: 0, syncing: false, lastError: null };

function haptic() {
  if (Platform.OS !== 'web') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => undefined);
}

export default function HydrationScreen() {
  const { user } = useAuth();
  const { isGuest, gate } = useAccountGate();
  const live = useHydration();
  const h = isGuest ? SAMPLE : live;
  const { state: weather } = useWeather({ enabled: !isGuest, withForecast: false });
  const { width, height } = useWindowDimensions();
  const [amount, setAmount] = useState(250);
  const [customOpen, setCustomOpen] = useState(false);

  const tz = user?.timezone ?? 'UTC';
  useEffect(() => {
    if (!isGuest) void initHydration(tz);
  }, [tz, isGuest]);
  useEffect(() => setHydrationTimeZone(tz), [tz]);

  // Re-sync when the screen regains focus (e.g. goal changed on Profile) or the app returns to the foreground.
  useFocusEffect(useCallback(() => void sync(), [])); // no-op for guests (store never initialised)
  useEffect(() => {
    const sub = AppState.addEventListener('change', (s) => s === 'active' && void sync());
    return () => sub.remove();
  }, []);

  const glassWidth = Math.min(width * 0.45, (height * 0.38) * 0.66, 220);
  const remaining = Math.max(h.goalMl - h.totalMl, 0);
  const shownTotal = useCountUp(h.totalMl);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <AppText variant="heading">{isGuest ? 'Welcome' : `Hi ${user?.first_name}`}</AppText>
        <View style={styles.headerRight}>
          <WeatherChip state={isGuest ? SAMPLE_WEATHER_CHIP : weather} units={user?.units ?? 'metric'}
            onPress={gate(() => router.push('/weather-location'))} />
          {isGuest ? (
            <View style={styles.badge} accessibilityLabel="Sample data">
              <AppText style={styles.badgeText}>Sample</AppText>
            </View>
          ) : (
            <SyncBadge pending={h.pendingCount} syncing={h.syncing} />
          )}
        </View>
      </View>

      <View style={styles.center}>
        <View style={styles.totalRow} accessible accessibilityLabel={`${h.totalMl} millilitres of ${h.goalMl}`}>
          <AppText variant="display" style={styles.numeral}>{shownTotal.toLocaleString()}</AppText>
          <AppText style={styles.unit}>ml</AppText>
        </View>
        <AppText variant="caption">
          {isGuest
            ? 'Sign in to track your own water'
            : remaining > 0 ? `${remaining.toLocaleString()} ml to your ${h.goalMl.toLocaleString()} ml goal` : 'Goal reached — nice work!'}
        </AppText>

        {!isGuest && weather.status === 'ready' && weather.current.hydration_tip && (
          <AppText variant="caption" style={styles.status}>💧 {weather.current.hydration_tip}</AppText>
        )}

        <View style={styles.glass}>
          <WaterGlass width={glassWidth} progress={h.goalMl ? h.totalMl / h.goalMl : 0} />
        </View>

        <View style={styles.chips} accessibilityRole="radiogroup">
          {CHIPS.map((ml) => (
            <Pressable key={ml} accessibilityRole="radio" accessibilityState={{ selected: amount === ml }}
              onPress={gate(() => setAmount(ml))} style={[styles.chip, amount === ml && styles.chipOn]}>
              <AppText style={styles.chipLabel}>{ml} ml</AppText>
            </Pressable>
          ))}
        </View>

        <View style={styles.actions}>
          <Pressable accessibilityRole="button" accessibilityLabel="Undo last drink" disabled={!h.entries.length}
            onPress={gate(() => { haptic(); void undoLast(); })}
            style={({ pressed }) => [styles.round, styles.roundWash, !h.entries.length && styles.dim, pressed && styles.pressed]}>
            <UndoIcon color={colors.accentIcon} />
          </Pressable>
          <Button title={`+ WATER`} accessibilityLabel={`Add ${amount} millilitres`} style={styles.add}
            onPress={gate(() => { haptic(); void addWater(amount); })} />
          <Pressable accessibilityRole="button" accessibilityLabel="Custom amount" onPress={gate(() => setCustomOpen(true))}
            style={({ pressed }) => [styles.round, styles.roundSoft, pressed && styles.pressed]}>
            <AppText style={styles.dots}>•••</AppText>
          </Pressable>
        </View>

        {h.lastError && <AppText variant="caption" style={styles.status}>{h.lastError}</AppText>}
      </View>

      <CustomAmount visible={customOpen} onClose={() => setCustomOpen(false)}
        onAdd={(ml) => { setCustomOpen(false); haptic(); void addWater(ml); }} />
    </SafeAreaView>
  );
}

function SyncBadge({ pending, syncing }: { pending: number; syncing: boolean }) {
  if (!pending) return null;
  return (
    <View style={styles.badge} accessibilityLabel={`${pending} changes waiting to sync`}>
      <AppText style={styles.badgeText}>{syncing ? 'Syncing…' : `${pending} to sync`}</AppText>
    </View>
  );
}

function CustomAmount({ visible, onClose, onAdd }: { visible: boolean; onClose: () => void; onAdd: (ml: number) => void }) {
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);
  const submit = () => {
    const ml = Number(value);
    if (!Number.isInteger(ml) || ml < 1 || ml > 5000) return setError('Enter a whole number from 1 to 5000.');
    setValue('');
    setError(null);
    onAdd(ml);
  };
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose} accessibilityLabel="Close">
        <Pressable style={styles.sheet} onPress={() => undefined}>
          <AppText variant="heading">Custom amount</AppText>
          <TextField label="Millilitres" value={value} onChangeText={(t) => setValue(t.replace(/\D/g, '').slice(0, 4))}
            keyboardType="number-pad" autoFocus error={error} onSubmitEditing={submit} />
          <Button title="ADD" onPress={submit} />
          <Button title="Cancel" variant="ghost" onPress={onClose} />
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  headerRight: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 24, paddingTop: 8 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 24, gap: 6 },
  totalRow: { flexDirection: 'row', alignItems: 'baseline', gap: 6 },
  unit: { fontFamily: fonts.heavy, fontSize: 28 },
  numeral: { fontVariant: ['tabular-nums'] }, // digits don't jiggle while counting
  glass: { marginVertical: 18 },
  chips: { flexDirection: 'row', gap: 15, marginBottom: 18 },
  chip: { width: 82, height: 38, borderRadius: radius.pill, backgroundColor: colors.chip, alignItems: 'center', justifyContent: 'center' },
  chipOn: { backgroundColor: colors.chipSelected, borderWidth: 2, borderColor: colors.primary },
  chipLabel: { fontFamily: fonts.bold, fontSize: 16 },
  actions: { flexDirection: 'row', alignItems: 'center', gap: 18 },
  round: { width: 48, height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center' },
  roundWash: { backgroundColor: colors.accentWash },
  roundSoft: { backgroundColor: colors.accentSoft },
  dots: { fontFamily: fonts.heavy, color: colors.navy, fontSize: 14, letterSpacing: 1 },
  add: { width: 180, height: 62 },
  pressed: { transform: [{ scale: 0.94 }] },
  dim: { opacity: 0.4 },
  status: { marginTop: 10, textAlign: 'center' },
  badge: { backgroundColor: colors.accentSoft, borderRadius: radius.pill, paddingHorizontal: 12, paddingVertical: 4 },
  badgeText: { fontFamily: fonts.bold, fontSize: 13, color: colors.tabActive },
  backdrop: { flex: 1, backgroundColor: 'rgba(11,30,55,0.35)', justifyContent: 'center', padding: 24 },
  sheet: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: 24, gap: 14, width: '100%', maxWidth: 420, alignSelf: 'center' },
});
