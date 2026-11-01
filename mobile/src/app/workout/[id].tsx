import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Alert, ScrollView, StyleSheet, useWindowDimensions, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Svg, { Polyline, Rect } from 'react-native-svg';

import { Button } from '@/components/ui/button';
import { AppText } from '@/components/ui/text';
import { api, ApiError, WorkoutDetail } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { ACTIVITY_LABEL, SOURCE_LABEL } from '@/lib/fitness-labels';
import { formatDistance, formatDuration, formatPace, projectRoute } from '@/lib/geo';
import { colors, fonts, radius } from '@/theme/tokens';

export default function WorkoutScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { user } = useAuth();
  const { width } = useWindowDimensions();
  const [w, setW] = useState<WorkoutDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.workout(id).then(setW).catch((e) => setError(e instanceof ApiError ? e.userMessage : 'Could not load workout.'));
  }, [id]);

  const mapW = Math.min(width - 48, 480);
  const mapH = Math.round(mapW * 0.7);
  const units = user?.units ?? 'metric';

  function confirmDelete() {
    Alert.alert('Delete workout?', 'This permanently deletes the workout and its route.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete', style: 'destructive', onPress: async () => {
          try {
            await api.deleteWorkout(id);
            router.back();
          } catch (e) {
            setError(e instanceof ApiError ? e.userMessage : 'Could not delete.');
          }
        },
      },
    ]);
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.head}>
          <AppText variant="title">{w ? ACTIVITY_LABEL[w.activity_type] : 'Workout'}</AppText>
          <Button title="Done" variant="ghost" onPress={() => router.back()} />
        </View>
        {error && <AppText variant="error">{error}</AppText>}
        {!w ? (!error && <ActivityIndicator color={colors.primary} />) : (
          <>
            <AppText variant="caption">
              {new Date(w.started_at).toLocaleString(undefined, { dateStyle: 'full', timeStyle: 'short' })} · {SOURCE_LABEL[w.source] ?? w.source}
            </AppText>
            {w.route.length > 1 ? (
              <Svg width={mapW} height={mapH} accessibilityLabel="Route drawing">
                <Rect x={0} y={0} width={mapW} height={mapH} rx={radius.md} fill={colors.accentWash} />
                {projectRoute(w.route, mapW, mapH, 18).map((pts, i) => (
                  <Polyline key={i} points={pts} fill="none" stroke={colors.primary} strokeWidth={4}
                    strokeLinecap="round" strokeLinejoin="round" />
                ))}
              </Svg>
            ) : w.source === 'gps' ? <AppText variant="caption">No route was recorded.</AppText> : null}
            <View style={styles.grid}>
              <Stat label="Distance" value={formatDistance(w.distance_m, units)} />
              <Stat label="Time" value={formatDuration(w.active_duration_s)} />
              <Stat label="Pace" value={formatPace(w.distance_m, w.active_duration_s) ?? '—'} />
              <Stat label="Calories" value={w.calories_kcal_estimate != null ? `≈ ${Math.round(w.calories_kcal_estimate)} kcal` : '—'} />
              {w.steps != null && <Stat label="Steps" value={w.steps.toLocaleString()} />}
            </View>
            <AppText variant="caption">
              Calories are an estimate based on activity type, time and the body weight in your settings.
            </AppText>
            <Button title="Delete workout" variant="ghost" onPress={confirmDelete} />
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
      <AppText style={styles.value}>{value}</AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  content: { padding: 24, gap: 14, alignItems: 'stretch' },
  head: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  stat: { flexBasis: '47%', flexGrow: 1, backgroundColor: colors.accentWash, borderRadius: radius.md, padding: 14, gap: 2 },
  value: { fontFamily: fonts.heavy, fontSize: 20, fontVariant: ['tabular-nums'] },
});
