import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, FlatList, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/button';
import { AppText } from '@/components/ui/text';
import { api, ApiError, Payment } from '@/lib/api';
import { colors, fonts } from '@/theme/tokens';

const STORES: Record<string, string> = { app_store: 'App Store', play_store: 'Google Play', stripe: 'Card', promotional: 'Promotional' };
const KINDS: Record<string, string> = { initial_purchase: 'Subscribed', renewal: 'Renewal', restore: 'Restored', product_change: 'Plan change' };

function amount(p: Payment) {
  if (p.amount === null) return '—';
  const n = Number(p.amount);
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency: p.currency ?? 'USD' }).format(n);
  } catch {
    return `${n.toFixed(2)} ${p.currency ?? ''}`;
  }
}

export default function Payments() {
  const [items, setItems] = useState<Payment[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.payments().then(setItems).catch((e) => setError(e instanceof ApiError ? e.userMessage : 'Could not load payments.'));
  }, []);

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <AppText variant="title">Payments</AppText>
        <Button title="Done" variant="ghost" onPress={() => router.back()} />
      </View>
      {error ? (
        <AppText variant="error" style={styles.pad}>{error}</AppText>
      ) : !items ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: 40 }} />
      ) : (
        <FlatList
          data={items}
          keyExtractor={(p) => p.id}
          contentContainerStyle={styles.pad}
          ListEmptyComponent={<AppText variant="caption">No payments yet.</AppText>}
          ListFooterComponent={items.length ? (
            <AppText variant="caption" style={styles.note}>
              Payments are processed by the app store, which emails you the official invoice.
            </AppText>
          ) : undefined}
          renderItem={({ item: p }) => (
            <View style={styles.row} accessible
              accessibilityLabel={`${KINDS[p.kind] ?? p.kind}, ${amount(p)}, ${new Date(p.purchased_at).toLocaleDateString()}, ${p.status}`}>
              <View style={styles.flex}>
                <AppText style={styles.title}>{KINDS[p.kind] ?? p.kind}</AppText>
                <AppText variant="caption">
                  {new Date(p.purchased_at).toLocaleDateString()} · {STORES[p.provider] ?? p.provider}
                  {p.environment === 'sandbox' ? ' · Test' : ''}
                </AppText>
                {p.receipt_number && <AppText variant="caption">Receipt {p.receipt_number}</AppText>}
              </View>
              <View style={styles.right}>
                <AppText style={styles.title}>{amount(p)}</AppText>
                {p.status !== 'succeeded' && (
                  <AppText style={[styles.status, p.status === 'refunded' && { color: colors.danger }]}>
                    {p.status.charAt(0).toUpperCase() + p.status.slice(1)}
                  </AppText>
                )}
              </View>
            </View>
          )}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 24, paddingTop: 8 },
  pad: { padding: 24, gap: 4 },
  row: { flexDirection: 'row', paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: colors.border, gap: 12 },
  flex: { flex: 1, gap: 2 },
  right: { alignItems: 'flex-end', gap: 2 },
  title: { fontFamily: fonts.bold },
  status: { fontFamily: fonts.bold, fontSize: 13, color: colors.navySoft },
  note: { marginTop: 16 },
});
