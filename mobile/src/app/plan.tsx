import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Alert, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/button';
import { AppText } from '@/components/ui/text';
import { api, ApiError, CalendarStatus, Recommendation, Recommendations } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { CONNECT_MESSAGES, runGoogleConsent } from '@/lib/google-connect';
import { addWater } from '@/lib/hydration-store';
import { colors, fonts, radius } from '@/theme/tokens';

const ICON: Record<string, string> = { hydration: '💧', walking: '🚶', jogging: '🏃', running: '🏃' };

function hm(iso: string) {
  return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

export default function Plan() {
  const { user } = useAuth();
  const premium = user?.plan === 'premium';
  const [recs, setRecs] = useState<Recommendations | null>(null);
  const [cal, setCal] = useState<CalendarStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [r, c] = await Promise.all([api.recommendations(), api.calendarStatus()]);
      setRecs(r);
      setCal(c);
    } catch (e) {
      if (e instanceof ApiError && e.code === 'calendar_reconnect') {
        setCal({ connected: true, status: 'revoked', can_read_free_busy: false, can_add_events: false });
      }
      setError(e instanceof ApiError ? e.userMessage : 'Could not load your plan.');
    }
  }, []);

  useFocusEffect(useCallback(() => void load(), [load]));

  async function connect(authUrl?: string) {
    setBusy('connect');
    try {
      const outcome = await runGoogleConsent(authUrl);
      if (CONNECT_MESSAGES[outcome]) setError(CONNECT_MESSAGES[outcome]);
      await load();
      return outcome;
    } catch (e) {
      setError(e instanceof ApiError ? e.userMessage : 'Could not connect.');
      return 'error' as const;
    } finally {
      setBusy(null);
    }
  }

  async function addToCalendar(r: Recommendation) {
    setBusy(r.id);
    setError(null);
    try {
      await api.scheduleRecommendation(r.id);
      await load();
    } catch (e) {
      if (e instanceof ApiError && e.code === 'needs_calendar_permission' && typeof e.extra.auth_url === 'string') {
        // Incremental consent: ask for "add events" only now, then retry once.
        setBusy(null);
        if ((await connect(e.extra.auth_url)) === 'ok') return addToCalendar(r);
        return;
      }
      setError(e instanceof ApiError ? e.userMessage : 'Could not add it.');
    } finally {
      setBusy(null);
    }
  }

  async function dismiss(r: Recommendation) {
    setBusy(r.id);
    try {
      await api.dismissRecommendation(r.id);
      await load();
    } finally {
      setBusy(null);
    }
  }

  function logWater(r: Recommendation) {
    void addWater(250);
    Alert.alert('Logged 250 ml', 'Nice — keep it up.');
    void dismiss(r);
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <ScrollView contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => {
          setRefreshing(true);
          await load();
          setRefreshing(false);
        }} />}>
        <View style={styles.head}>
          <AppText variant="title">Today&apos;s plan</AppText>
          <Button title="Done" variant="ghost" onPress={() => router.back()} />
        </View>

        {cal && (!cal.connected || cal.status !== 'active') && (
          <View style={styles.card}>
            <AppText variant="heading">{cal.connected ? 'Reconnect Google Calendar' : 'Connect Google Calendar'}</AppText>
            <AppText variant="caption">
              We only read when you&apos;re busy or free — never your event titles or details — to suggest good moments
              for water and exercise.
            </AppText>
            <Button title={cal.connected ? 'Reconnect' : 'Connect Google Calendar'} onPress={() => connect()} loading={busy === 'connect'} />
          </View>
        )}
        {recs && !recs.calendar_used && (
          <AppText variant="caption">Without a calendar we plan around your waking hours only.</AppText>
        )}
        {error && <AppText variant="error">{error}</AppText>}

        {!recs ? <ActivityIndicator color={colors.primary} /> : (
          <>
            {recs.items.length === 0 && <AppText variant="caption">Nothing more to suggest today. Enjoy your evening!</AppText>}
            {recs.items.map((r) => (
              <View key={r.id} style={styles.item}>
                <AppText style={styles.icon}>{ICON[r.kind] ?? '•'}</AppText>
                <View style={styles.flex}>
                  <AppText style={styles.title}>{hm(r.start)} · {r.title}</AppText>
                  <AppText variant="caption">{r.reason}</AppText>
                  {r.status === 'scheduled' && <AppText style={styles.scheduled}>In your Google Calendar ✓</AppText>}
                  {r.status === 'suggested' && (
                    <View style={styles.actions}>
                      {r.kind === 'hydration' ? (
                        <Button title="Log 250 ml" variant="secondary" style={styles.small} onPress={() => logWater(r)} disabled={busy === r.id} />
                      ) : (
                        <Button title="Add to calendar" variant="secondary" style={styles.small} loading={busy === r.id}
                          onPress={() => addToCalendar(r)} disabled={!cal?.connected} />
                      )}
                      <Button title="Dismiss" variant="ghost" style={styles.small} onPress={() => dismiss(r)} disabled={busy === r.id} />
                    </View>
                  )}
                </View>
              </View>
            ))}
            {!premium && recs.premium_ideas_available > 0 && (
              <View style={styles.card}>
                <AppText variant="heading">
                  {recs.premium_ideas_available} workout idea{recs.premium_ideas_available === 1 ? '' : 's'} for today
                </AppText>
                <AppText variant="caption">
                  Premium suggests walks and runs in your free time when the weather is right, and adds them to your calendar.
                </AppText>
                <Button title="SEE PREMIUM" onPress={() => router.push('/premium')} />
              </View>
            )}
          </>
        )}
        <Button title="Plan settings" variant="ghost" onPress={() => router.push('/plan-settings')} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  content: { padding: 24, gap: 12, paddingBottom: 48 },
  head: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  card: { backgroundColor: colors.accentWash, borderRadius: radius.md, padding: 16, gap: 10 },
  item: { flexDirection: 'row', gap: 12, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: colors.border },
  icon: { fontSize: 24, lineHeight: 30 },
  flex: { flex: 1, gap: 4 },
  title: { fontFamily: fonts.bold },
  scheduled: { fontFamily: fonts.bold, color: colors.tabActive },
  actions: { flexDirection: 'row', gap: 4, marginTop: 4, flexWrap: 'wrap' },
  small: { minHeight: 40, paddingHorizontal: 16 },
});
