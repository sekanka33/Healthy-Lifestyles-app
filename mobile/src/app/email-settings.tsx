import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Switch, View } from 'react-native';

import { Button } from '@/components/ui/button';
import { FormScreen } from '@/components/ui/screen';
import { AppText } from '@/components/ui/text';
import { api, ApiError, EmailPrefs, Frequency, ReportKind } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { colors, fonts, radius } from '@/theme/tokens';

const FREQS: { v: Frequency; l: string }[] = [
  { v: 'off', l: 'Off' }, { v: 'daily', l: 'Daily' }, { v: 'weekly', l: 'Weekly' }, { v: 'monthly', l: 'Monthly' },
];
const REPORTS: { kind: ReportKind; field: 'water_summary' | 'fitness_report' | 'medication_report'; title: string; premium: boolean }[] = [
  { kind: 'water', field: 'water_summary', title: 'Water report', premium: false },
  { kind: 'fitness', field: 'fitness_report', title: 'Fitness report', premium: true },
  { kind: 'medication', field: 'medication_report', title: 'Medication report', premium: true },
];

export default function EmailSettings() {
  const { user } = useAuth();
  const premium = user?.plan === 'premium';
  const [prefs, setPrefs] = useState<EmailPrefs | null>(null);
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);
  const [sending, setSending] = useState<ReportKind | null>(null);

  useEffect(() => {
    api.emailPrefs().then(setPrefs).catch(() => setMessage({ text: 'Could not load email settings.', error: true }));
  }, []);

  async function update(patch: Partial<EmailPrefs>) {
    if (!prefs) return;
    const before = prefs;
    setPrefs({ ...prefs, ...patch }); // optimistic
    try {
      setPrefs(await api.setEmailPrefs(patch));
    } catch (e) {
      setPrefs(before);
      setMessage({ text: e instanceof ApiError ? e.userMessage : 'Could not save.', error: true });
    }
  }

  async function sendNow(kind: ReportKind) {
    setSending(kind);
    setMessage(null);
    try {
      const r = await api.emailReport(kind, 'this_week');
      setMessage({ text: `This week's report is on its way to ${r.to}.` });
    } catch (e) {
      setMessage({ text: e instanceof ApiError ? e.userMessage : 'Could not send.', error: true });
    } finally {
      setSending(null);
    }
  }

  if (!prefs) return <FormScreen>{message && <AppText variant="error">{message.text}</AppText>}</FormScreen>;

  return (
    <FormScreen>
      <AppText variant="title">Email & reports</AppText>
      <AppText variant="caption">Reports arrive at 7am your time and include a PDF. Sent to {user?.email}.</AppText>

      {REPORTS.map((r) => {
        const locked = r.premium && !premium;
        return (
          <View key={r.kind} style={[styles.block, locked && styles.dim]}>
            <AppText variant="heading">{r.title}{locked ? ' · Premium' : ''}</AppText>
            <View style={styles.wrap} accessibilityRole="radiogroup">
              {FREQS.map((f) => (
                <Pressable key={f.v} accessibilityRole="radio" accessibilityState={{ selected: prefs[r.field] === f.v, disabled: locked }}
                  disabled={locked} onPress={() => update({ [r.field]: f.v } as Partial<EmailPrefs>)}
                  style={[styles.chip, prefs[r.field] === f.v && styles.chipOn]}>
                  <AppText style={styles.chipText}>{f.l}</AppText>
                </Pressable>
              ))}
            </View>
            {locked ? (
              <Button title="See Premium" variant="ghost" onPress={() => router.push('/premium')} />
            ) : (
              <Button title="Email me this week's report" variant="ghost" loading={sending === r.kind}
                onPress={() => sendNow(r.kind)} />
            )}
          </View>
        );
      })}

      {premium && (
        <Row title="Include medication names in emails"
          detail="Off: emails show only your overall percentage; details stay in the app. On: names and a PDF are included."
          value={prefs.medication_report_detail === 'detailed'}
          onChange={(v) => update({ medication_report_detail: v ? 'detailed' : 'summary_only' })} />
      )}
      <Row title="Subscription emails" detail="Renewal reminders and billing problems. Receipts and security emails are always sent."
        value={prefs.subscription_lifecycle_emails} onChange={(v) => update({ subscription_lifecycle_emails: v })} />
      <Row title="Product news" detail="Occasional updates about new features. Off unless you turn it on."
        value={prefs.product_updates} onChange={(v) => update({ product_updates: v })} />

      {message && <AppText variant={message.error ? 'error' : 'caption'}>{message.text}</AppText>}
      <Button title="Done" variant="ghost" onPress={() => router.back()} />
    </FormScreen>
  );
}

function Row({ title, detail, value, onChange }: { title: string; detail: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <View style={styles.row}>
      <View style={styles.flex}>
        <AppText style={styles.rowTitle}>{title}</AppText>
        <AppText variant="caption">{detail}</AppText>
      </View>
      <Switch value={value} onValueChange={onChange} trackColor={{ true: colors.primary }} accessibilityLabel={title} />
    </View>
  );
}

const styles = StyleSheet.create({
  block: { gap: 8, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: colors.border },
  dim: { opacity: 0.6 },
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { minHeight: 40, paddingHorizontal: 14, borderRadius: radius.pill, backgroundColor: colors.chip, justifyContent: 'center' },
  chipOn: { backgroundColor: colors.chipSelected, borderWidth: 2, borderColor: colors.primary },
  chipText: { fontFamily: fonts.bold },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 8 },
  flex: { flex: 1, gap: 2 },
  rowTitle: { fontFamily: fonts.bold },
});
