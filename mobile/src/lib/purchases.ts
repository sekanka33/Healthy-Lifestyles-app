/**
 * Thin wrapper around RevenueCat's SDK (react-native-purchases).
 *
 * The device only *starts* purchases. Whether the user is Premium is decided by our backend, which
 * re-checks RevenueCat server-to-server (POST /billing/sync and webhooks). Nothing here unlocks a
 * feature by itself.
 *
 * Needs a development build for real purchases (Expo Go runs RevenueCat in preview mode only).
 * Public SDK keys are designed to ship in apps; the secret key lives only on the backend.
 */
import { Linking, Platform } from 'react-native';
import Purchases, { PURCHASES_ERROR_CODE, PurchasesError, PurchasesPackage } from 'react-native-purchases';

import { api, BillingStatus } from './api';

const API_KEY = Platform.select({
  ios: process.env.EXPO_PUBLIC_REVENUECAT_IOS_KEY,
  android: process.env.EXPO_PUBLIC_REVENUECAT_ANDROID_KEY,
  default: undefined,
});

let configuredFor: string | null = null;

/** False on web and in builds without RevenueCat keys: the paywall explains instead of crashing. */
export function purchasesAvailable(): boolean {
  return Platform.OS !== 'web' && !!API_KEY;
}

/** Identify the signed-in user to RevenueCat with our user id (what our webhooks map back to). */
export async function identifyPurchaser(userId: string): Promise<void> {
  if (!purchasesAvailable() || configuredFor === userId) return;
  try {
    if (configuredFor === null && !(await Purchases.isConfigured())) {
      Purchases.configure({ apiKey: API_KEY!, appUserID: userId });
    } else {
      await Purchases.logIn(userId);
    }
    configuredFor = userId;
  } catch (e) {
    console.warn('RevenueCat setup failed', e);
  }
}

export async function forgetPurchaser(): Promise<void> {
  if (!configuredFor) return;
  configuredFor = null;
  await Purchases.logOut().catch(() => undefined); // throws if already anonymous — harmless
}

/** The monthly Premium package from the current offering (price comes from the store, localized). */
export async function getPremiumPackage(): Promise<PurchasesPackage | null> {
  if (!purchasesAvailable()) return null;
  const offerings = await Purchases.getOfferings();
  const current = offerings.current;
  return current?.monthly ?? current?.availablePackages[0] ?? null;
}

export type PurchaseOutcome =
  | { kind: 'cancelled' }
  | { kind: 'done'; status: BillingStatus }
  | { kind: 'pending' } // e.g. Ask to Buy / slow card: access arrives later via webhook
  | { kind: 'error'; message: string };

function isPurchasesError(e: unknown): e is PurchasesError {
  return typeof e === 'object' && e !== null && 'code' in e;
}

async function confirmWithServer(): Promise<PurchaseOutcome> {
  try {
    return { kind: 'done', status: await api.billingSync() };
  } catch {
    // The store took the payment; our server will still learn about it from the webhook.
    return { kind: 'pending' };
  }
}

export async function buy(pkg: PurchasesPackage): Promise<PurchaseOutcome> {
  try {
    await Purchases.purchasePackage(pkg);
  } catch (e) {
    if (isPurchasesError(e)) {
      if (e.code === PURCHASES_ERROR_CODE.PURCHASE_CANCELLED_ERROR || e.userCancelled) return { kind: 'cancelled' };
      if (e.code === PURCHASES_ERROR_CODE.PAYMENT_PENDING_ERROR) return { kind: 'pending' };
      return { kind: 'error', message: e.message || 'The purchase could not be completed.' };
    }
    return { kind: 'error', message: 'The purchase could not be completed.' };
  }
  return confirmWithServer();
}

export async function restore(): Promise<PurchaseOutcome> {
  try {
    await Purchases.restorePurchases();
  } catch (e) {
    return { kind: 'error', message: isPurchasesError(e) && e.message ? e.message : 'Restore failed.' };
  }
  return confirmWithServer();
}

/** Opens the store's own subscription management (cancel, change, billing details). */
export async function manageSubscription(): Promise<void> {
  if (purchasesAvailable()) {
    try {
      const info = await Purchases.getCustomerInfo();
      if (info.managementURL) return void (await Linking.openURL(info.managementURL));
      if (Platform.OS === 'ios') return void (await Purchases.showManageSubscriptions());
    } catch {
      // fall through to the generic store pages
    }
  }
  await Linking.openURL(Platform.OS === 'ios'
    ? 'https://apps.apple.com/account/subscriptions'
    : 'https://play.google.com/store/account/subscriptions');
}
