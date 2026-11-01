import { router, useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/button';
import { WeatherCard } from '@/components/weather-card';
import { AppText } from '@/components/ui/text';
import { useAccountGate } from '@/hooks/use-account-gate';
import { useWeather } from '@/hooks/use-weather';
import { Activity, api, ApiError, CurrentWeather, FitnessSummary, Forecast, Workout } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { ACTIVITY_LABEL, SOURCE_LABEL } from '@/lib/fitness-labels';
import { formatDistance, formatDuration, formatPace } from '@/lib/geo';
import {
  activeSeconds,
  discardWorkout,
  finishWorkout,
  loadActiveWorkout,
  LocationPermissionError,
  pauseWorkout,
  resumePendingWork,
  resumeWorkout,
  startWorkout,
  useActiveWorkout,
} from '@/lib/workout-tracker';
import { colors, fonts, radius } from '@/theme/tokens';

const ACTIVITIES: { value: Activity; label: string }[] = [
  { value: 'walking', label: 'Walk' },
  { value: 'jogging', label: 'Jog' },
  { value: 'running', label: 'Run' },
];

const SAMPLE_WEATHER: { current: CurrentWeather; forecast: Forecast | null } = {
  current: {
    lat: 0, lon: 0, place_name: 'Your area', observed_at: null, temp_c: 21, feels_like_c: 21, humidity: 45, wind_mps: 3,
    wind_gust_mps: null, rain_mm_1h: 0, condition: { code: 801, main: 'Clouds', description: 'few clouds', icon: '02d' },
    sunrise: null, sunset: null, is_day: true, hydration_tip: null, stale: false,
    outdoor: { score: 100, label: 'good', reasons: ['Great conditions'] },
  },
  forecast: null,
};
const SAMPLE_SUMMARY = { workouts: 3, distance_km: 8.4, active_minutes: 95 };
const SAMPLE_WORKOUTS = [
  { id: 's1', label: 'Walk', when: 'Today, 07:10', distance: '3.20 km', time: '38:12' },
  { id: 's2', label: 'Run', when: 'Yesterday, 18:05', distance: '5.20 km', time: '29:40' },
];

function when(iso: string) {
  return new Date(iso).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

export default function Fitness() {
  const { user } = useAuth();
  const { isGuest, needsVerification, gate } = useAccountGate();
  const premium = !isGuest && user?.plan === 'premium';
  const units = user?.units ?? 'metric';
  const active = useActiveWorkout();
  const [summary, setSummary] = useState<FitnessSummary | null>(null);
  const [recent, setRecent] = useState<Workout[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [, setTick] = useState(0);
  // Current weather is free for any verified account; the hourly forecast is Premium.
  const { state: weather, reload: reloadWeather } = useWeather({ enabled: !isGuest && !active, withForecast: premium });
  const chooseLocation = gate(() => router.push('/weather-location'));

  const load = useCallback(async () => {
    if (!premium) return;
    setError(null);
    try {
      const [s, w] = await Promise.all([api.fitnessSummary('weekly'), api.workouts()]);
      setSummary(s);
      setRecent(w.slice(0, 10));
    } catch (e) {
      setError(e instanceof ApiError ? e.userMessage : 'Could not load workouts.');
    }
  }, [premium]);

  useFocusEffect(useCallback(() => {
    if (!premium) return;
    void loadActiveWorkout();
    void resumePendingWork().then((saved) => saved && load());
    void load();
  }, [premium, load]));

  // Live timer while recording.
  useEffect(() => {
    if (!active || active.state === 'finishing') return;
    const t = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [active]);

  async function start(activity: Activity) {
    setBusy(true);
    setError(null);
    try {
      await startWorkout(activity);
    } catch (e) {
      if (e instanceof LocationPermissionError) {
        Alert.alert('Location needed', `${e.message} You can allow it in Settings.`);
      } else {
        setError('Could not start GPS. Try again outdoors with a clear view of the sky.');
      }
    } finally {
      setBusy(false);
    }
  }

  async function finish() {
    setBusy(true);
    try {
      const saved = await finishWorkout();
      await load();
      router.push({ pathname: '/workout/[id]', params: { id: saved.id } });
    } catch (e) {
      setError(e instanceof ApiError ? e.userMessage : 'Saved on this phone. It will upload when you are back online.');
    } finally {
      setBusy(false);
    }
  }

  function confirmDiscard() {
    Alert.alert('Discard workout?', 'This recording will be deleted.', [
      { text: 'Keep recording', style: 'cancel' },
      { text: 'Discard', style: 'destructive', onPress: () => void discardWorkout() },
    ]);
  }

  // ---------------------------------------------------------------- guests & free plan: labelled preview
  if (!premium) {
    const upsell = gate(() => router.push('/premium'));
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <ScrollView contentContainerStyle={styles.content}>
          <AppText variant="title">Move</AppText>
          <WeatherCard state={weather} units={units} onChooseLocation={chooseLocation} onRetry={reloadWeather}
            sample={isGuest ? SAMPLE_WEATHER : undefined} />
          <Pressable accessibilityRole="button" onPress={gate(() => router.push('/plan'))} style={styles.planCard}>
            <View style={styles.flex}>
              <AppText variant="heading">Today&apos;s plan</AppText>
              <AppText variant="caption">Water breaks and workout ideas that fit your calendar and the weather.</AppText>
            </View>
            <AppText style={styles.chev}>›</AppText>
          </Pressable>
          <View style={styles.card}>
            <AppText variant="heading">Track walks, jogs & runs</AppText>
            <AppText variant="caption">
              Record your route with GPS, see distance and pace, set weekly goals and keep everything in one place.
              Part of Premium.
            </AppText>
            <Button title={needsVerification ? 'VERIFY EMAIL TO GET STARTED' : isGuest ? 'SIGN IN TO GET STARTED' : 'SEE PREMIUM'}
              onPress={upsell} />
          </View>
          <View style={styles.startRow}>
            {ACTIVITIES.map((a) => (
              <Button key={a.value} title={a.label} variant="secondary" style={styles.startBtn} onPress={upsell} />
            ))}
          </View>
          <View style={styles.head}>
            <AppText variant="heading">This week</AppText>
            <View style={styles.badge}><AppText style={styles.badgeText}>Sample</AppText></View>
          </View>
          <Stats workouts={SAMPLE_SUMMARY.workouts} distance={`${SAMPLE_SUMMARY.distance_km} km`} minutes={SAMPLE_SUMMARY.active_minutes} />
          {SAMPLE_WORKOUTS.map((w) => (
            <Pressable key={w.id} onPress={upsell} style={styles.row} accessibilityRole="button">
              <View style={styles.flex}>
                <AppText style={styles.bold}>{w.label}</AppText>
                <AppText variant="caption">{w.when}</AppText>
              </View>
              <AppText style={styles.bold}>{w.distance}</AppText>
              <AppText variant="caption">  {w.time}</AppText>
            </Pressable>
          ))}
        </ScrollView>
      </SafeAreaView>
    );
  }

  // ---------------------------------------------------------------- recording
  if (active) {
    const secs = activeSeconds(active);
    const pace = formatPace(active.distanceM, secs);
    const gpsWeak = active.state === 'running' && (active.accuracyM == null || active.accuracyM > 35);
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <ScrollView contentContainerStyle={[styles.content, styles.live]}>
          <AppText variant="label">{ACTIVITY_LABEL[active.activity]} · {active.state === 'paused' ? 'Paused' : active.state === 'finishing' ? 'Saving' : 'Recording'}</AppText>
          <AppText variant="display" style={styles.tabular} accessibilityLabel={`Time ${formatDuration(secs)}`}>{formatDuration(secs)}</AppText>
          <View style={styles.liveStats}>
            <LiveStat label="Distance" value={formatDistance(active.distanceM, units)} />
            <LiveStat label="Pace" value={pace ?? '—'} />
          </View>
          {gpsWeak && <AppText variant="caption">Searching for a strong GPS signal…</AppText>}
          {active.foregroundOnly && active.state === 'running' && (
            <AppText variant="caption" style={styles.center}>
              Background location is off, so keep the app open while you move (or allow &quot;Always&quot; in Settings).
            </AppText>
          )}
          {error && <AppText variant="error" style={styles.center}>{error}</AppText>}
          {active.state === 'finishing' ? (
            <Button title="TRY SAVING AGAIN" onPress={finish} loading={busy} />
          ) : (
            <View style={styles.liveActions}>
              {active.state === 'running'
                ? <Button title="PAUSE" variant="secondary" onPress={pauseWorkout} style={styles.flex} />
                : <Button title="RESUME" variant="secondary" onPress={resumeWorkout} style={styles.flex} />}
              <Button title="FINISH" onPress={finish} loading={busy} style={styles.flex} />
            </View>
          )}
          {active.state !== 'finishing' && <Button title="Discard" variant="ghost" onPress={confirmDiscard} />}
          <AppText variant="caption" style={styles.center}>The distance is finalised from your route when you finish.</AppText>
        </ScrollView>
      </SafeAreaView>
    );
  }

  // ---------------------------------------------------------------- overview
  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => {
          setRefreshing(true);
          await Promise.all([load(), reloadWeather()]);
          setRefreshing(false);
        }} />}>
        <AppText variant="title">Move</AppText>
        <WeatherCard state={weather} units={units} onChooseLocation={chooseLocation} onRetry={reloadWeather} />
        <Pressable accessibilityRole="button" onPress={gate(() => router.push('/plan'))} style={styles.planCard}>
        <View style={styles.flex}>
          <AppText variant="heading">Today&apos;s plan</AppText>
          <AppText variant="caption">Water breaks and workout ideas that fit your calendar and the weather.</AppText>
        </View>
        <AppText style={styles.chev}>›</AppText>
        </Pressable>
        <AppText variant="heading">Start a workout</AppText>
        <View style={styles.startRow}>
          {ACTIVITIES.map((a) => (
            <Button key={a.value} title={a.label} style={styles.startBtn} disabled={busy} onPress={() => start(a.value)} />
          ))}
        </View>
        <Button title="Log a workout manually" variant="ghost" onPress={() => router.push('/workout-manual')} />
        {error && <AppText variant="error">{error}</AppText>}

        {!summary || !recent ? <ActivityIndicator color={colors.primary} /> : (
          <>
            <View style={styles.head}>
              <AppText variant="heading">This week</AppText>
              <Button title="Goals" variant="ghost" style={styles.small} onPress={() => router.push('/fitness-settings')} />
            </View>
            <Stats workouts={summary.workouts} distance={formatDistance(summary.distance_km * 1000, units)} minutes={summary.active_minutes} />
            {summary.goals.map((g) => (
              <View key={g.id} style={styles.goal} accessibilityLabel={`Goal ${Math.round(Math.min(g.progress, 1) * 100)} percent`}>
                <AppText variant="caption">
                  {g.metric === 'distance_km' ? `${g.current_value} / ${g.target_value} km`
                    : g.metric === 'workout_count' ? `${g.current_value} / ${g.target_value} workouts`
                      : `${g.current_value} / ${g.target_value} active minutes`}
                </AppText>
                <View style={styles.track}><View style={[styles.fill, { width: `${Math.min(g.progress, 1) * 100}%` }]} /></View>
              </View>
            ))}
            {summary.calories_kcal_estimate != null && (
              <AppText variant="caption">≈ {Math.round(summary.calories_kcal_estimate)} kcal burned (estimate)</AppText>
            )}

            <AppText variant="heading" style={styles.gapTop}>Recent</AppText>
            {recent.length === 0 && <AppText variant="caption">No workouts yet. Start one above!</AppText>}
            {recent.map((w) => (
              <Pressable key={w.id} accessibilityRole="button" onPress={() => router.push({ pathname: '/workout/[id]', params: { id: w.id } })}
                style={({ pressed }) => [styles.row, pressed && styles.pressed]}>
                <View style={styles.flex}>
                  <AppText style={styles.bold}>{ACTIVITY_LABEL[w.activity_type]}</AppText>
                  <AppText variant="caption">{when(w.started_at)} · {SOURCE_LABEL[w.source] ?? w.source}</AppText>
                </View>
                <AppText style={styles.bold}>{formatDistance(w.distance_m, units)}</AppText>
                <AppText variant="caption">  {formatDuration(w.active_duration_s)}</AppText>
              </Pressable>
            ))}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function Stats({ workouts, distance, minutes }: { workouts: number; distance: string; minutes: number }) {
  return (
    <View style={styles.stats}>
      <Stat label="Workouts" value={String(workouts)} />
      <Stat label="Distance" value={distance} />
      <Stat label="Active" value={`${Math.round(minutes)} min`} />
    </View>
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

function LiveStat({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.liveStat}>
      <AppText style={[styles.liveValue, styles.tabular]}>{value}</AppText>
      <AppText variant="label">{label}</AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  content: { padding: 24, gap: 12, paddingBottom: 48 },
  live: { alignItems: 'center', gap: 16, paddingTop: 48 },
  center: { textAlign: 'center' },
  tabular: { fontVariant: ['tabular-nums'] },
  liveStats: { flexDirection: 'row', gap: 32 },
  liveStat: { alignItems: 'center' },
  liveValue: { fontFamily: fonts.heavy, fontSize: 28 },
  liveActions: { flexDirection: 'row', gap: 12, alignSelf: 'stretch' },
  card: { backgroundColor: colors.accentWash, borderRadius: radius.md, padding: 16, gap: 10 },
  planCard: { flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: 16 },
  chev: { fontFamily: fonts.heavy, fontSize: 24, color: colors.textMuted },
  startRow: { flexDirection: 'row', gap: 10 },
  startBtn: { flex: 1, paddingHorizontal: 8 },
  head: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 8 },
  small: { minHeight: 36 },
  badge: { backgroundColor: colors.accentSoft, borderRadius: radius.pill, paddingHorizontal: 12, paddingVertical: 4 },
  badgeText: { fontFamily: fonts.bold, fontSize: 13, color: colors.tabActive },
  stats: { flexDirection: 'row', gap: 10 },
  stat: { flex: 1, backgroundColor: colors.accentWash, borderRadius: radius.md, padding: 12, gap: 2 },
  statValue: { fontFamily: fonts.heavy, fontSize: 18 },
  goal: { gap: 6 },
  track: { height: 8, borderRadius: 4, backgroundColor: colors.glassBody, overflow: 'hidden' },
  fill: { height: '100%', backgroundColor: colors.primary, borderRadius: 4 },
  gapTop: { marginTop: 12 },
  row: { flexDirection: 'row', alignItems: 'center', paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: colors.border },
  flex: { flex: 1 },
  bold: { fontFamily: fonts.bold },
  pressed: { opacity: 0.6 },
});
