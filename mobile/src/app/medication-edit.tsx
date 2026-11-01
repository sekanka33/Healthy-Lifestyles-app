import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, StyleSheet, Switch, View } from 'react-native';

import { Button } from '@/components/ui/button';
import { FormScreen } from '@/components/ui/screen';
import { AppText } from '@/components/ui/text';
import { TextField } from '@/components/ui/text-field';
import { api, ApiError, Medication, MedicationInput, ScheduleType } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { requestReminderPermission, syncMedicationReminders } from '@/lib/medication-reminders';
import { colors, fonts, radius } from '@/theme/tokens';

const TYPES: { value: ScheduleType; label: string }[] = [
  { value: 'daily', label: 'Every day' },
  { value: 'specific_days', label: 'Some days' },
  { value: 'every_n_days', label: 'Every few days' },
  { value: 'as_needed', label: 'As needed' },
];
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;
const YMD = /^\d{4}-\d{2}-\d{2}$/;

function normaliseTime(raw: string): string | null {
  const m = raw.trim().match(/^(\d{1,2})[:.]?(\d{2})$/);
  if (!m) return null;
  const t = `${m[1].padStart(2, '0')}:${m[2]}`;
  return HHMM.test(t) ? t : null;
}

export default function MedicationEdit() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  const { user } = useAuth();
  const [loaded, setLoaded] = useState(!id);
  const [existing, setExisting] = useState<Medication | null>(null);
  const [name, setName] = useState('');
  const [instructions, setInstructions] = useState('');
  const [notes, setNotes] = useState('');
  const [type, setType] = useState<ScheduleType>('daily');
  const [times, setTimes] = useState<string[]>(['08:00']);
  const [newTime, setNewTime] = useState('');
  const [days, setDays] = useState<number[]>([1, 2, 3, 4, 5]);
  const [intervalDays, setIntervalDays] = useState('2');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [reminders, setReminders] = useState(true);
  const [errors, setErrors] = useState<Record<string, string | null>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!id) return;
    api.medication(id).then((m) => {
      setExisting(m);
      setName(m.name);
      setInstructions(m.dosage_instructions);
      setNotes(m.notes ?? '');
      setType(m.schedule_type);
      setTimes(m.times.length ? m.times : ['08:00']);
      setDays(m.days_of_week ?? [1, 2, 3, 4, 5]);
      setIntervalDays(String(m.interval_days ?? 2));
      setStartDate(m.start_date);
      setEndDate(m.end_date ?? '');
      setReminders(m.reminders_enabled);
      setLoaded(true);
    }).catch((e) => setErrors({ form: e instanceof ApiError ? e.userMessage : 'Could not load.' }));
  }, [id]);

  function addTime() {
    const t = normaliseTime(newTime);
    if (!t) return setErrors({ ...errors, time: 'Use 24-hour time, e.g. 08:00 or 20:30.' });
    setTimes([...new Set([...times, t])].sort());
    setNewTime('');
    setErrors({ ...errors, time: null });
  }

  async function save() {
    const e: Record<string, string | null> = {
      name: name.trim() ? null : 'Enter the medication name.',
      instructions: instructions.trim() ? null : 'Enter the dose and instructions from your prescription.',
      times: type !== 'as_needed' && !times.length ? 'Add at least one time.' : null,
      days: type === 'specific_days' && !days.length ? 'Choose at least one day.' : null,
      interval: type === 'every_n_days' && !(Number(intervalDays) >= 2 && Number(intervalDays) <= 90) ? 'Between 2 and 90 days.' : null,
      startDate: startDate && !YMD.test(startDate) ? 'Use YYYY-MM-DD.' : null,
      endDate: endDate && !YMD.test(endDate) ? 'Use YYYY-MM-DD.' : (endDate && startDate && endDate < startDate ? 'Must be after the start date.' : null),
    };
    setErrors(e);
    if (Object.values(e).some(Boolean)) return;

    const body: MedicationInput = {
      name: name.trim(),
      dosage_instructions: instructions.trim(),
      notes: notes.trim() || null,
      schedule_type: type,
      times: type === 'as_needed' ? [] : times,
      days_of_week: type === 'specific_days' ? days : null,
      interval_days: type === 'every_n_days' ? Number(intervalDays) : null,
      end_date: endDate || null,
      reminders_enabled: reminders,
      ...(startDate ? { start_date: startDate } : {}),
    };
    setBusy(true);
    try {
      if (reminders && type !== 'as_needed') {
        const ok = await requestReminderPermission();
        if (!ok) Alert.alert('Notifications are off', 'Turn on notifications for this app in Settings to get reminders.');
      }
      if (existing) await api.updateMedication(existing.id, body);
      else await api.createMedication({ ...body, timezone: user?.timezone });
      if (user) void syncMedicationReminders(user.timezone).catch(() => undefined);
      router.back();
    } catch (err) {
      setErrors({ form: err instanceof ApiError ? err.userMessage : 'Could not save.' });
    } finally {
      setBusy(false);
    }
  }

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      if (user) void syncMedicationReminders(user.timezone).catch(() => undefined);
      router.back();
    } catch (err) {
      setErrors({ form: err instanceof ApiError ? err.userMessage : 'Something went wrong.' });
    } finally {
      setBusy(false);
    }
  }

  function confirmDelete() {
    if (!existing) return;
    Alert.alert('Delete medication?', `This permanently deletes ${existing.name} and its dose history. To keep the history, use "Stop taking" instead.`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: () => void act(() => api.deleteMedication(existing.id)) },
    ]);
  }

  if (!loaded) {
    return <FormScreen>{errors.form ? <AppText variant="error">{errors.form}</AppText> : <ActivityIndicator color={colors.primary} />}</FormScreen>;
  }

  return (
    <FormScreen>
      <AppText variant="title">{existing ? 'Edit medication' : 'Add medication'}</AppText>
      <AppText variant="caption">Enter it exactly as your doctor or pharmacist prescribed. The app never changes your dose.</AppText>

      <TextField label="Name" value={name} onChangeText={setName} error={errors.name} placeholder="e.g. Metformin" />
      <TextField label="Dose & instructions" value={instructions} onChangeText={setInstructions} multiline
        error={errors.instructions} placeholder="e.g. 500 mg with breakfast" style={styles.multiline} />
      <TextField label="Notes (optional)" value={notes} onChangeText={setNotes} multiline style={styles.multiline} />

      <AppText variant="label">How often</AppText>
      <View style={styles.wrap} accessibilityRole="radiogroup">
        {TYPES.map((t) => (
          <Pressable key={t.value} accessibilityRole="radio" accessibilityState={{ selected: type === t.value }}
            onPress={() => setType(t.value)} style={[styles.chip, type === t.value && styles.chipOn]}>
            <AppText style={styles.chipText}>{t.label}</AppText>
          </Pressable>
        ))}
      </View>

      {type === 'specific_days' && (
        <>
          <View style={styles.wrap}>
            {DAYS.map((label, i) => {
              const day = i + 1;
              const on = days.includes(day);
              return (
                <Pressable key={label} accessibilityRole="checkbox" accessibilityState={{ checked: on }}
                  onPress={() => setDays(on ? days.filter((d) => d !== day) : [...days, day].sort())}
                  style={[styles.day, on && styles.chipOn]}>
                  <AppText style={styles.chipText}>{label}</AppText>
                </Pressable>
              );
            })}
          </View>
          {errors.days && <AppText variant="error">{errors.days}</AppText>}
        </>
      )}
      {type === 'every_n_days' && (
        <TextField label="Every how many days?" value={intervalDays} keyboardType="number-pad" error={errors.interval}
          onChangeText={(t) => setIntervalDays(t.replace(/\D/g, '').slice(0, 2))} />
      )}

      {type !== 'as_needed' && (
        <>
          <AppText variant="label">Times (your local time, {user?.timezone})</AppText>
          <View style={styles.wrap}>
            {times.map((t) => (
              <Pressable key={t} accessibilityRole="button" accessibilityLabel={`Remove ${t}`}
                onPress={() => setTimes(times.filter((x) => x !== t))} style={[styles.chip, styles.chipOn]}>
                <AppText style={styles.chipText}>{t}  ✕</AppText>
              </Pressable>
            ))}
          </View>
          <View style={styles.row}>
            <View style={styles.flex}>
              <TextField label="Add a time" value={newTime} onChangeText={setNewTime} placeholder="20:00"
                keyboardType="numbers-and-punctuation" error={errors.time ?? errors.times} onSubmitEditing={addTime} />
            </View>
            <Button title="Add" variant="secondary" onPress={addTime} style={styles.addBtn} />
          </View>
        </>
      )}

      <View style={styles.row}>
        <View style={styles.flex}>
          <TextField label="Start date" value={startDate} onChangeText={setStartDate} placeholder="Today"
            hint="YYYY-MM-DD" error={errors.startDate} />
        </View>
        <View style={styles.flex}>
          <TextField label="End date (optional)" value={endDate} onChangeText={setEndDate} placeholder="Ongoing"
            hint="YYYY-MM-DD" error={errors.endDate} />
        </View>
      </View>

      {type !== 'as_needed' && (
        <View style={styles.switchRow}>
          <View style={styles.flex}>
            <AppText style={styles.switchLabel}>Reminders</AppText>
            <AppText variant="caption">A notification at each dose time. It won&apos;t show the medication name.</AppText>
          </View>
          <Switch value={reminders} onValueChange={setReminders} trackColor={{ true: colors.primary }}
            accessibilityLabel="Reminders" />
        </View>
      )}

      {errors.form && <AppText variant="error">{errors.form}</AppText>}
      <Button title={existing ? 'SAVE CHANGES' : 'ADD MEDICATION'} onPress={save} loading={busy} />
      {existing && (existing.active ? (
        <Button title="Stop taking (keep history)" variant="secondary" disabled={busy}
          onPress={() => act(() => api.discontinueMedication(existing.id))} />
      ) : (
        <Button title="Start taking again" variant="secondary" disabled={busy}
          onPress={() => act(() => api.resumeMedication(existing.id))} />
      ))}
      {existing && <Button title="Delete medication" variant="ghost" disabled={busy} onPress={confirmDelete} />}
      <Button title="Cancel" variant="ghost" onPress={() => router.back()} />
    </FormScreen>
  );
}

const styles = StyleSheet.create({
  multiline: { minHeight: 76, paddingTop: 14, textAlignVertical: 'top' },
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { minHeight: 40, paddingHorizontal: 14, borderRadius: radius.pill, backgroundColor: colors.chip, justifyContent: 'center' },
  chipOn: { backgroundColor: colors.chipSelected, borderWidth: 2, borderColor: colors.primary },
  chipText: { fontFamily: fonts.bold },
  day: { width: 52, minHeight: 40, borderRadius: radius.pill, backgroundColor: colors.chip, alignItems: 'center', justifyContent: 'center' },
  row: { flexDirection: 'row', gap: 12, alignItems: 'flex-start' },
  flex: { flex: 1 },
  addBtn: { marginTop: 22, minHeight: 52 },
  switchRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  switchLabel: { fontFamily: fonts.bold },
});
