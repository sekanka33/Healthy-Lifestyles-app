import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Alert, Pressable, StyleSheet, View } from 'react-native';

import { Button } from '@/components/ui/button';
import { FormScreen } from '@/components/ui/screen';
import { AppText } from '@/components/ui/text';
import { TextField } from '@/components/ui/text-field';
import { Activity, api, ApiError, CalendarStatus, SchedulingPrefs } from '@/lib/api';
import { CONNECT_MESSAGES, runGoogleConsent } from '@/lib/google-connect';
import { colors, fonts, radius } from '@/theme/tokens';

const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;
const ACTS: { v: Activity; l: string }[] = [{ v: 'walking', l: 'Walk' }, { v: 'jogging', l: 'Jog' }, { v: 'running', l: 'Run' }];
const TIMES = [{ v: 'morning', l: 'Morning' }, { v: 'afternoon', l: 'Afternoon' }, { v: 'evening', l: 'Evening' }] as const;
const short = (t: string | null) => (t ? t.slice(0, 5) : '');

export default function PlanSettings() {
  const [prefs, setPrefs] = useState<SchedulingPrefs | null>(null);
  const [cal, setCal] = useState<CalendarStatus | null>(null);
  const [wake, setWake] = useState('');
  const [sleep, setSleep] = useState('');
  const [workStart, setWorkStart] = useState('');
  const [workEnd, setWorkEnd] = useState('');
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    Promise.all([api.schedulingPrefs(), api.calendarStatus()]).then(([p, c]) => {
      setPrefs(p);
      setCal(c);
      setWake(short(p.sleep_end));
      setSleep(short(p.sleep_start));
      setWorkStart(short(p.working_hours_start));
      setWorkEnd(short(p.working_hours_end));
    }).catch(() => setMessage({ text: 'Could not load settings.', error: true }));
  }, []);

  function toggle<T extends string>(list: T[], v: T): T[] {
    return list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
  }

  async function save() {
    if (!prefs) return;
    for (const [label, v] of [['Wake-up', wake], ['Bedtime', sleep]] as const) {
      if (!HHMM.test(v)) return setMessage({ text: `${label} must look like 07:00.`, error: true });
    }
    if ((workStart || workEnd) && !(HHMM.test(workStart) && HHMM.test(workEnd))) {
      return setMessage({ text: 'Set both working-hours times (e.g. 09:00 and 17:00), or leave both empty.', error: true });
    }
    setBusy(true);
    setMessage(null);
    try {
      const saved = await api.setSchedulingPrefs({
        sleep_end: `${wake}:00`, sleep_start: `${sleep}:00`,
        working_hours_start: workStart ? `${workStart}:00` : null, working_hours_end: workEnd ? `${workEnd}:00` : null,
        min_free_slot_minutes: prefs.min_free_slot_minutes, preferred_activities: prefs.preferred_activities,
        preferred_activity_times: prefs.preferred_activity_times,
      });
      setPrefs(saved);
      setMessage({ text: 'Saved.' });
    } catch (e) {
      setMessage({ text: e instanceof ApiError ? e.userMessage : 'Could not save.', error: true });
    } finally {
      setBusy(false);
    }
  }

  async function connect() {
    try {
      const outcome = await runGoogleConsent();
      if (CONNECT_MESSAGES[outcome]) setMessage({ text: CONNECT_MESSAGES[outcome]!, error: true });
      setCal(await api.calendarStatus());
    } catch (e) {
      setMessage({ text: e instanceof ApiError ? e.userMessage : 'Could not connect.', error: true });
    }
  }

  function disconnect() {
    Alert.alert('Disconnect Google Calendar?', 'We’ll revoke our access and delete the stored connection.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Disconnect', style: 'destructive', onPress: async () => {
        await api.disconnectCalendar().catch(() => undefined);
        setCal(await api.calendarStatus());
      } },
    ]);
  }

  if (!prefs) return <FormScreen>{message ? <AppText variant="error">{message.text}</AppText> : null}</FormScreen>;

  return (
    <FormScreen>
      <AppText variant="title">Plan settings</AppText>

      <AppText variant="heading">Google Calendar</AppText>
      {cal?.connected && cal.status === 'active' ? (
        <>
          <AppText variant="caption">Connected · reading free/busy times{cal.can_add_events ? ' · can add events you approve' : ''}.</AppText>
          <Button title="Disconnect" variant="ghost" onPress={disconnect} />
        </>
      ) : (
        <Button title={cal?.connected ? 'Reconnect Google Calendar' : 'Connect Google Calendar'} variant="secondary" onPress={connect} />
      )}

      <AppText variant="heading" style={styles.gap}>Your day</AppText>
      <View style={styles.row}>
        <View style={styles.flex}><TextField label="Wake-up" value={wake} onChangeText={setWake} placeholder="06:30" /></View>
        <View style={styles.flex}><TextField label="Bedtime" value={sleep} onChangeText={setSleep} placeholder="22:00" /></View>
      </View>
      <View style={styles.row}>
        <View style={styles.flex}><TextField label="Work starts" value={workStart} onChangeText={setWorkStart} placeholder="09:00" /></View>
        <View style={styles.flex}><TextField label="Work ends" value={workEnd} onChangeText={setWorkEnd} placeholder="17:00" /></View>
      </View>
      <AppText variant="caption">Workout ideas avoid working hours; water breaks can still fit in.</AppText>

      <AppText variant="label">Shortest free time worth suggesting</AppText>
      <View style={styles.wrap}>
        {[15, 30, 45, 60].map((m) => (
          <Chip key={m} label={`${m} min`} on={prefs.min_free_slot_minutes === m}
            onPress={() => setPrefs({ ...prefs, min_free_slot_minutes: m })} />
        ))}
      </View>

      <AppText variant="label">Activities you enjoy</AppText>
      <View style={styles.wrap}>
        {ACTS.map((a) => (
          <Chip key={a.v} label={a.l} on={prefs.preferred_activities.includes(a.v)}
            onPress={() => setPrefs({ ...prefs, preferred_activities: toggle(prefs.preferred_activities, a.v) })} />
        ))}
      </View>
      <AppText variant="label">Favourite times</AppText>
      <View style={styles.wrap}>
        {TIMES.map((t) => (
          <Chip key={t.v} label={t.l} on={prefs.preferred_activity_times.includes(t.v)}
            onPress={() => setPrefs({ ...prefs, preferred_activity_times: toggle(prefs.preferred_activity_times, t.v) })} />
        ))}
      </View>

      {message && <AppText variant={message.error ? 'error' : 'caption'}>{message.text}</AppText>}
      <Button title="SAVE" onPress={save} loading={busy} />
      <Button title="Done" variant="ghost" onPress={() => router.back()} />
    </FormScreen>
  );
}

function Chip({ label, on, onPress }: { label: string; on: boolean; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: on }} onPress={onPress}
      style={[styles.chip, on && styles.chipOn]}>
      <AppText style={styles.chipText}>{label}</AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  gap: { marginTop: 12 },
  row: { flexDirection: 'row', gap: 12 },
  flex: { flex: 1 },
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { minHeight: 40, paddingHorizontal: 14, borderRadius: radius.pill, backgroundColor: colors.chip, justifyContent: 'center' },
  chipOn: { backgroundColor: colors.chipSelected, borderWidth: 2, borderColor: colors.primary },
  chipText: { fontFamily: fonts.bold },
});
