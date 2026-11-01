import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/button';
import { AppText } from '@/components/ui/text';
import { useAccountGate } from '@/hooks/use-account-gate';
import { AdherenceRow, api, ApiError, Medication, ScheduledDose } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { clearMedicationReminders, syncMedicationReminders } from '@/lib/medication-reminders';
import { colors, fonts, radius } from '@/theme/tokens';

const DISCLAIMER = "Always follow your healthcare professional's instructions. This app records what you enter; it doesn't give medical advice.";

function timeOf(iso: string) {
  return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

const today = new Date();
const at = (h: number, m: number) => new Date(today.getFullYear(), today.getMonth(), today.getDate(), h, m).toISOString();
const SAMPLE_DOSES: ScheduledDose[] = [
  { medication_id: 's1', medication_name: 'Vitamin D', dosage_instructions: '1 capsule with breakfast', scheduled_for: at(8, 0), status: 'taken', recorded_at: at(8, 5), note: null },
  { medication_id: 's2', medication_name: 'Example medication', dosage_instructions: 'As prescribed by your doctor', scheduled_for: at(13, 0), status: 'upcoming', recorded_at: null, note: null },
  { medication_id: 's2', medication_name: 'Example medication', dosage_instructions: 'As prescribed by your doctor', scheduled_for: at(21, 0), status: 'upcoming', recorded_at: null, note: null },
];

export default function Medications() {
  const { user } = useAuth();
  const { isGuest, needsVerification, gate } = useAccountGate();
  const premium = !isGuest && user?.plan === 'premium';
  const [doses, setDoses] = useState<ScheduledDose[] | null>(null);
  const [meds, setMeds] = useState<Medication[] | null>(null);
  const [adherence, setAdherence] = useState<AdherenceRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [pending, setPending] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!premium || !user) return;
    setError(null);
    try {
      const [d, m, a] = await Promise.all([api.medicationSchedule(), api.medications(), api.adherence()]);
      setDoses(d);
      setMeds(m);
      setAdherence(a.medications);
      void syncMedicationReminders(user.timezone, m).catch(() => undefined);
    } catch (e) {
      setError(e instanceof ApiError ? e.userMessage : 'Could not load medications.');
    }
  }, [premium, user]);

  useFocusEffect(useCallback(() => {
    if (premium) void load();
    else if (!isGuest) void clearMedicationReminders(); // plan lapsed: stop reminding
  }, [premium, isGuest, load]));

  async function mark(d: ScheduledDose, status: 'taken' | 'skipped') {
    const key = d.medication_id + d.scheduled_for;
    setPending(key);
    try {
      if (d.status === status) await api.clearDose(d.medication_id, d.scheduled_for); // tap again to undo
      else await api.recordDose(d.medication_id, d.scheduled_for, status);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.userMessage : 'Could not save.');
    } finally {
      setPending(null);
    }
  }

  // Guests and free users see a labelled preview; their buttons lead to sign-in or Premium.
  if (!premium) {
    const upsell = gate(() => router.push('/premium'));
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <ScrollView contentContainerStyle={styles.content}>
          <AppText variant="title">Medication</AppText>
          <View style={styles.card}>
            <AppText variant="heading">Never lose track of a dose</AppText>
            <AppText variant="caption">
              Add your medications exactly as prescribed, get reminders at the right local time, and log each dose as
              taken or skipped. Part of Premium.
            </AppText>
            <Button title={needsVerification ? 'VERIFY EMAIL TO GET STARTED' : isGuest ? 'SIGN IN TO GET STARTED' : 'SEE PREMIUM'} onPress={upsell} />
          </View>
          <View style={styles.sectionHead}>
            <AppText variant="heading">Today</AppText>
            <View style={styles.sampleBadge}><AppText style={styles.sampleText}>Sample</AppText></View>
          </View>
          {SAMPLE_DOSES.map((d) => (
            <DoseRow key={d.medication_id + d.scheduled_for} dose={d} onTake={upsell} onSkip={upsell} />
          ))}
          <AppText variant="caption" style={styles.disclaimer}>{DISCLAIMER}</AppText>
        </ScrollView>
      </SafeAreaView>
    );
  }

  const active = (meds ?? []).filter((m) => m.active);
  const stopped = (meds ?? []).filter((m) => !m.active);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => {
          setRefreshing(true);
          await load();
          setRefreshing(false);
        }} />}>
        <View style={styles.sectionHead}>
          <AppText variant="title">Medication</AppText>
          <Button title="+ Add" variant="secondary" style={styles.addBtn} onPress={() => router.push('/medication-edit')} />
        </View>
        {error && <AppText variant="error">{error}</AppText>}

        {!doses || !meds ? (
          <ActivityIndicator color={colors.primary} style={{ marginTop: 32 }} />
        ) : (
          <>
            <AppText variant="heading">Today</AppText>
            {doses.length === 0 ? (
              <AppText variant="caption">{active.length ? 'No scheduled doses today.' : 'Add a medication to see your doses here.'}</AppText>
            ) : doses.map((d) => (
              <DoseRow key={d.medication_id + d.scheduled_for} dose={d} busy={pending === d.medication_id + d.scheduled_for}
                onTake={() => mark(d, 'taken')} onSkip={() => mark(d, 'skipped')} />
            ))}

            <AppText variant="heading" style={styles.gapTop}>Your medications</AppText>
            {active.map((m) => <MedRow key={m.id} med={m} />)}
            {stopped.length > 0 && <AppText variant="label" style={styles.gapTop}>Stopped</AppText>}
            {stopped.map((m) => <MedRow key={m.id} med={m} />)}

            {adherence.some((a) => a.scheduled > 0) && (
              <>
                <AppText variant="heading" style={styles.gapTop}>Last 7 days</AppText>
                {adherence.filter((a) => a.scheduled > 0).map((a) => (
                  <View key={a.medication_id} style={styles.adhRow}
                    accessibilityLabel={`${a.medication_name}: ${a.taken} of ${a.scheduled} taken, ${a.skipped} skipped, ${a.missed} missed, ${a.unrecorded} not logged`}>
                    <AppText style={styles.medName}>{a.medication_name}</AppText>
                    <AppText variant="caption">
                      {a.taken}/{a.scheduled} taken · {a.skipped} skipped · {a.missed} missed · {a.unrecorded} not logged
                    </AppText>
                  </View>
                ))}
              </>
            )}
          </>
        )}
        <AppText variant="caption" style={styles.disclaimer}>{DISCLAIMER}</AppText>
      </ScrollView>
    </SafeAreaView>
  );
}

const STATUS_LABEL: Record<string, string> = {
  taken: 'Taken', skipped: 'Skipped', missed: 'Missed', upcoming: 'Upcoming', unrecorded: 'Not logged',
};

function DoseRow({ dose, onTake, onSkip, busy }: { dose: ScheduledDose; onTake: () => void; onSkip: () => void; busy?: boolean }) {
  const recorded = dose.status === 'taken' || dose.status === 'skipped' || dose.status === 'missed';
  return (
    <View style={styles.dose}>
      <View style={styles.doseInfo}>
        <AppText style={styles.doseTime}>{timeOf(dose.scheduled_for)}</AppText>
        <AppText style={styles.medName}>{dose.medication_name}</AppText>
        <AppText variant="caption" numberOfLines={2}>{dose.dosage_instructions}</AppText>
        <AppText style={[styles.state, dose.status === 'taken' && styles.stateTaken,
          dose.status === 'unrecorded' && styles.stateWarn]}>{STATUS_LABEL[dose.status]}</AppText>
      </View>
      {busy ? <ActivityIndicator color={colors.primary} /> : (
        <View style={styles.doseActions}>
          <Pressable accessibilityRole="button" accessibilityLabel={`Mark ${dose.medication_name} taken`}
            accessibilityState={{ selected: dose.status === 'taken' }} onPress={onTake}
            style={[styles.pill, dose.status === 'taken' ? styles.pillOn : styles.pillOff]}>
            <AppText style={[styles.pillText, dose.status === 'taken' && styles.pillTextOn]}>Taken</AppText>
          </Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel={`Mark ${dose.medication_name} skipped`}
            accessibilityState={{ selected: dose.status === 'skipped' }} onPress={onSkip}
            style={[styles.pill, dose.status === 'skipped' ? styles.pillSkipOn : styles.pillOff]}>
            <AppText style={styles.pillText}>Skip</AppText>
          </Pressable>
        </View>
      )}
      {recorded && <AppText style={styles.undoHint}>Tap again to undo</AppText>}
    </View>
  );
}

function describe(m: Medication) {
  const times = m.times.join(', ');
  switch (m.schedule_type) {
    case 'daily': return `Every day at ${times}`;
    case 'specific_days': {
      const names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
      return `${(m.days_of_week ?? []).map((d) => names[d - 1]).join(', ')} at ${times}`;
    }
    case 'every_n_days': return `Every ${m.interval_days} days at ${times}`;
    default: return 'As needed';
  }
}

function MedRow({ med }: { med: Medication }) {
  return (
    <Pressable accessibilityRole="button" accessibilityHint="Edit medication"
      onPress={() => router.push({ pathname: '/medication-edit', params: { id: med.id } })}
      style={({ pressed }) => [styles.medRow, !med.active && styles.dim, pressed && styles.pressed]}>
      <View style={styles.flex}>
        <AppText style={styles.medName}>{med.name}</AppText>
        <AppText variant="caption">{describe(med)}{med.reminders_enabled && med.active ? ' · reminders on' : ''}</AppText>
      </View>
      <AppText style={styles.chevron}>›</AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  content: { padding: 24, gap: 12, paddingBottom: 48 },
  card: { backgroundColor: colors.accentWash, borderRadius: radius.md, padding: 16, gap: 10 },
  sectionHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  addBtn: { minHeight: 40, paddingHorizontal: 18 },
  sampleBadge: { backgroundColor: colors.accentSoft, borderRadius: radius.pill, paddingHorizontal: 12, paddingVertical: 4 },
  sampleText: { fontFamily: fonts.bold, fontSize: 13, color: colors.tabActive },
  gapTop: { marginTop: 12 },
  dose: { backgroundColor: colors.surface, borderRadius: radius.md, padding: 14, borderWidth: 1, borderColor: colors.border,
    flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 10 },
  doseInfo: { flex: 1, minWidth: 160, gap: 2 },
  doseTime: { fontFamily: fonts.heavy, fontSize: 18 },
  medName: { fontFamily: fonts.bold },
  state: { fontFamily: fonts.bold, fontSize: 13, color: colors.navySoft },
  stateTaken: { color: colors.tabActive },
  stateWarn: { color: colors.danger },
  doseActions: { flexDirection: 'row', gap: 8 },
  pill: { minHeight: 44, minWidth: 72, paddingHorizontal: 14, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center' },
  pillOff: { backgroundColor: colors.chip },
  pillOn: { backgroundColor: colors.primary },
  pillSkipOn: { backgroundColor: colors.chipSelected, borderWidth: 2, borderColor: colors.navySoft },
  pillText: { fontFamily: fonts.bold, color: colors.navy },
  pillTextOn: { color: colors.onPrimary },
  undoHint: { width: '100%', fontSize: 12, color: colors.textMuted },
  medRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: colors.border, gap: 8 },
  flex: { flex: 1, gap: 2 },
  chevron: { fontFamily: fonts.heavy, fontSize: 22, color: colors.textMuted },
  dim: { opacity: 0.55 },
  pressed: { opacity: 0.6 },
  adhRow: { gap: 2, paddingVertical: 6 },
  disclaimer: { marginTop: 16, fontSize: 12, lineHeight: 17 },
});
