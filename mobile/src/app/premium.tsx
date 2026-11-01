import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Alert, Linking, Platform, ScrollView, StyleSheet, View } from 'react-native';
import type { PurchasesPackage } from 'react-native-purchases';
import { SafeAreaView } from 'react-native-safe-area-context';

import { FeatureTable } from '@/components/feature-table';
import { DropIcon } from '@/components/icons';
import { Button } from '@/components/ui/button';
import { AppText } from '@/components/ui/text';
import { api, BillingStatus } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { buy, getPremiumPackage, manageSubscription, PurchaseOutcome, purchasesAvailable, restore } from '@/lib/purchases';
import { colors, radius } from '@/theme/tokens';


const TERMS_URL = process.env.EXPO_PUBLIC_TERMS_URL;
const PRIVACY_URL = process.env.EXPO_PUBLIC_PRIVACY_URL;
const STORE_ACCOUNT = Platform.OS === 'ios' ? 'Apple Account' : 'Google Play account';

function formatDate(iso: string | null) {
  return iso ? new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' }) : '';
}

export default function Premium() {
  const { reloadUser } = useAuth();
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [pkg, setPkg] = useState<PurchasesPackage | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<'buy' | 'restore' | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [s, p] = await Promise.all([api.billingStatus(), getPremiumPackage().catch(() => null)]);
        setStatus(s);
        setPkg(p);
      } catch {
        setError("Couldn't load your plan. Check your connection.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function handle(outcome: PurchaseOutcome) {
    if (outcome.kind === 'cancelled') return;
    if (outcome.kind === 'error') return setError(outcome.message);
    if (outcome.kind === 'pending') {
      Alert.alert('Almost there', "Your purchase is being confirmed. Premium will unlock as soon as the store confirms it.");
      return;
    }
    setStatus(outcome.status);
    await reloadUser().catch(() => undefined);
    if (outcome.status.plan === 'premium') {
      Alert.alert('Welcome to Premium', 'Thanks for subscribing!');
      router.back();
    } else {
      setError('No active Premium subscription was found for this account.');
    }
  }

  async function onBuy() {
    if (!pkg) return;
    setBusy('buy');
    setError(null);
    await handle(await buy(pkg));
    setBusy(null);
  }

  async function onRestore() {
    setBusy('restore');
    setError(null);
    await handle(await restore());
    setBusy(null);
  }

  const ent = status?.entitlement;
  const isPremium = status?.plan === 'premium';
  const price = pkg?.product.priceString;

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.hero}>
          <View style={styles.logo}><DropIcon size={34} color={colors.navy} /></View>
          <AppText variant="title" style={styles.center}>Healthy Lifestyles Premium</AppText>
          <AppText variant="caption" style={styles.center}>Everything in Free, plus the tools to move more and stay on track.</AppText>
        </View>

        <FeatureTable />

        {loading ? (
          <ActivityIndicator color={colors.primary} />
        ) : isPremium && ent ? (
          <View style={styles.card}>
            <AppText variant="heading">You&apos;re on Premium</AppText>
            <AppText variant="caption">
              {ent.status === 'grace_period'
                ? `There's a problem with your payment. Update it by ${formatDate(ent.expires_at)} to keep Premium.`
                : ent.will_renew
                  ? `Renews on ${formatDate(ent.expires_at)}.`
                  : ent.expires_at ? `Cancelled — Premium stays on until ${formatDate(ent.expires_at)}.` : 'Active.'}
            </AppText>
            {ent.environment === 'sandbox' && <AppText variant="caption">Test (sandbox) purchase.</AppText>}
            <Button title="Manage subscription" variant="secondary" onPress={() => manageSubscription()} />
          </View>
        ) : !purchasesAvailable() ? (
          <View style={styles.card}>
            <AppText variant="heading">Not available in this build</AppText>
            <AppText variant="caption">
              Subscriptions need the iOS or Android app built with store billing (a development or store build).
            </AppText>
          </View>
        ) : (
          <>
            {ent?.status === 'billing_issue' && (
              <AppText variant="error">Your last payment failed. Update your payment method in your {STORE_ACCOUNT} to resubscribe.</AppText>
            )}
            <Button title={price ? `SUBSCRIBE · ${price} / month` : 'SUBSCRIBE'} onPress={onBuy}
              loading={busy === 'buy'} disabled={!pkg || busy !== null} />
            {!pkg && <AppText variant="caption" style={styles.center}>Plans couldn&apos;t be loaded from the store right now.</AppText>}
            <Button title="Restore purchases" variant="ghost" onPress={onRestore} loading={busy === 'restore'} disabled={busy !== null} />
          </>
        )}

        {error && <AppText variant="error" accessibilityLiveRegion="polite">{error}</AppText>}

        {!isPremium && (
          <AppText style={styles.legal}>
            {price ? `Premium costs ${price} per month. ` : ''}Payment is charged to your {STORE_ACCOUNT} when you confirm.
            The subscription renews automatically each month unless cancelled at least 24 hours before the end of the
            current period. Cancel any time in your {STORE_ACCOUNT} settings; you keep Premium until the period ends.
          </AppText>
        )}
        <View style={styles.links}>
          {TERMS_URL && <Button title="Terms of Use" variant="ghost" onPress={() => Linking.openURL(TERMS_URL)} />}
          {PRIVACY_URL && <Button title="Privacy Policy" variant="ghost" onPress={() => Linking.openURL(PRIVACY_URL)} />}
        </View>
        <Button title="Not now" variant="ghost" onPress={() => router.back()} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  content: { padding: 24, gap: 16, maxWidth: 520, width: '100%', alignSelf: 'center' },
  hero: { alignItems: 'center', gap: 8 },
  logo: { width: 72, height: 72, borderRadius: 36, backgroundColor: colors.waterMarker, alignItems: 'center', justifyContent: 'center' },
  center: { textAlign: 'center' },
  card: { backgroundColor: colors.accentWash, borderRadius: radius.md, padding: 16, gap: 10 },
  legal: { fontSize: 12, lineHeight: 17, color: colors.textMuted },
  links: { flexDirection: 'row', justifyContent: 'center', flexWrap: 'wrap' },
});
