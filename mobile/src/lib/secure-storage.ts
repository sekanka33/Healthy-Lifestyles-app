import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

/**
 * Refresh tokens live in the iOS Keychain / Android Keystore via expo-secure-store.
 * The web build (dev only) has no secure store, so it falls back to localStorage.
 */
const options: SecureStore.SecureStoreOptions = {
  keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY,
};

export async function getSecret(key: string): Promise<string | null> {
  if (Platform.OS === 'web') return globalThis.localStorage?.getItem(key) ?? null;
  return SecureStore.getItemAsync(key, options);
}

export async function setSecret(key: string, value: string): Promise<void> {
  if (Platform.OS === 'web') return void globalThis.localStorage?.setItem(key, value);
  await SecureStore.setItemAsync(key, value, options);
}

export async function deleteSecret(key: string): Promise<void> {
  if (Platform.OS === 'web') return void globalThis.localStorage?.removeItem(key);
  await SecureStore.deleteItemAsync(key, options);
}
