import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Linking, Pressable, StyleSheet, Switch, View } from 'react-native';

import { Button } from '@/components/ui/button';
import { FormScreen } from '@/components/ui/screen';
import { AppText } from '@/components/ui/text';
import { TextField } from '@/components/ui/text-field';
import { api, ApiError, NotificationPrefs } from '@/lib/api';
import { syncHydrationReminders } from '@/lib/hydration-reminders';
import {
  DEFAULT_QUIET_END, DEFAULT_QUIET_START, formatClock, formatInterval, parseClock, reminderSlots,
} from '@/lib/hydration-schedule';
import { requestReminderPermission } from '@/lib/medication-reminders';
import { colors, fonts, radius } from '@/theme/tokens';

const INTERVALS = [60, 90, 120, 180, 240];

export default function HydrationReminderSettings() {
  const [prefs, setPrefs] = useState<NotificationPrefs | null>(null);
  const [quietStart, setQuietStart] = useState('');
  const [quietEnd, setQuietEnd] = useState('');
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);
  const [blocked, setBlocked] = useState(false);
  const [busy, setBusy] = useState(false);

  function showQuietHours(p: NotificationPrefs) {
    setQuietStart(formatClock(p.quiet_hours_start ?? DEFAULT_QUIET_START));
    setQuietEnd(formatClock(p.quiet_hours_end ?? DEFAULT_QUIET_END));
  }

  useEffect(() => {
    api.notificationPrefs().then((p) => {
      setPrefs(p);
      showQuietHours(p);
    }).catch(() => setMessage({ text: 'Could not load reminder settings.', error: true }));
  }, []);

  async function update(patch: Partial<NotificationPrefs>) {
    if (!prefs) return false;
    const before = prefs;
    setPrefs({ ...prefs, ...patch }); // optimistic
    setMessage(null);
    try {
      setPrefs(await api.setNotificationPrefs(patch));
    } catch (e) {
      setPrefs(before);
      setMessage({ text: e instanceof ApiError ? e.userMessage : 'Could not save.', error: true });
      return false;
    }
    await syncHydrationReminders().catch(() => setMessage({ text: 'Saved, but could not update your reminders.', error: true }));
    return true;
  }

  async function toggle(on: boolean) {
    setBlocked(false);
    if (on && !(await requestReminderPermission())) {
      setBlocked(true);
      return setMessage({ text: 'Notifications are off for LifePulse. Turn them on in your phone settings first.', error: true });
    }
    await update({ hydration_reminders_enabled: on });
  }

  if (!prefs) return <FormScreen>{message && <AppText variant="error">{message.text}</AppText>}</FormScreen>;

  const start = parseClock(quietStart);
  const end = parseClock(quietEnd);
  const savedStart = (prefs.quiet_hours_start ?? DEFAULT_QUIET_START).slice(0, 5);
  const savedEnd = (prefs.quiet_hours_end ?? DEFAULT_QUIET_END).slice(0, 5);
  const dirty = quietStart !== formatClock(savedStart) || quietEnd !== formatClock(savedEnd);
  const interval = prefs.hydration_reminder_interval_minutes;
  const slots = reminderSlots(interval, savedStart, savedEnd);
  const clock = (i: number) => formatClock(`${slots[i].hour}:${slots[i].minute}`);

  async function saveQuietHours() {
    if (!start || !end) return setMessage({ text: 'Enter times like 10:00 PM or 22:00.', error: true });
    if (start === end) return setMessage({ text: 'Quiet hours need a different start and end time.', error: true });
    setBusy(true);
    const saved = await update({ quiet_hours_start: `${start}:00`, quiet_hours_end: `${end}:00` });
    setBusy(false);
    if (saved) {
      setQuietStart(formatClock(start));
      setQuietEnd(formatClock(end));
      setMessage({ text: 'Quiet hours saved.' });
    }
  }

  return (
    <FormScreen>
      <AppText variant="title">Water reminders</AppText>

      <View style={styles.row}>
        <View style={styles.flex}>
          <AppText style={styles.rowTitle}>Remind me to drink water</AppText>
          <AppText variant="caption">Tap a reminder to go straight to your glass and log a drink.</AppText>
        </View>
        <Switch value={prefs.hydration_reminders_enabled} onValueChange={toggle}
          trackColor={{ true: colors.primary }} accessibilityLabel="Remind me to drink water" />
      </View>
      {blocked && <Button title="Open phone settings" variant="secondary" onPress={() => void Linking.openSettings()} />}

      <AppText variant="heading">How often</AppText>
      <View style={styles.wrap} accessibilityRole="radiogroup">
        {INTERVALS.map((m) => (
          <Pressable key={m} accessibilityRole="radio" accessibilityState={{ selected: interval === m }}
            onPress={() => void update({ hydration_reminder_interval_minutes: m })}
            style={[styles.chip, interval === m && styles.chipOn]}>
            <AppText style={styles.chipText}>{formatInterval(m)}</AppText>
          </Pressable>
        ))}
      </View>

      <AppText variant="heading">Quiet hours</AppText>
      <AppText variant="caption">No water reminders while you sleep. Set these to match your routine.</AppText>
      <View style={styles.times}>
        <View style={styles.flex}>
          <TextField label="From" value={quietStart} onChangeText={setQuietStart} placeholder="10:00 PM" />
        </View>
        <View style={styles.flex}>
          <TextField label="Until" value={quietEnd} onChangeText={setQuietEnd} placeholder="7:00 AM" />
        </View>
      </View>
      {dirty && <Button title="SAVE QUIET HOURS" onPress={saveQuietHours} loading={busy} />}

      {slots.length > 0 && (
        <AppText variant="caption">
          {slots.length === 1
            ? `You'll get 1 reminder a day, at ${clock(0)}.`
            : `You'll get ${slots.length} reminders a day, from ${clock(0)} to ${clock(slots.length - 1)}.`}
        </AppText>
      )}

      {message && <AppText variant={message.error ? 'error' : 'caption'}>{message.text}</AppText>}
      <Button title="Done" variant="ghost" onPress={() => router.back()} />
    </FormScreen>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 8 },
  times: { flexDirection: 'row', gap: 12 },
  flex: { flex: 1, gap: 2 },
  rowTitle: { fontFamily: fonts.bold },
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { minHeight: 40, paddingHorizontal: 14, borderRadius: radius.pill, backgroundColor: colors.chip, justifyContent: 'center' },
  chipOn: { backgroundColor: colors.chipSelected, borderWidth: 2, borderColor: colors.primary },
  chipText: { fontFamily: fonts.bold },
});
