import { useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { BackHandler } from 'react-native';

import { Button } from '@/components/ui/button';
import { FormScreen } from '@/components/ui/screen';
import { AppText } from '@/components/ui/text';
import { TextField } from '@/components/ui/text-field';
import { api, ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { validateCode } from '@/lib/validation';

const COOLDOWN_S = 60;

export default function VerifyEmail() {
  const { user, setUser, signOut } = useAuth();
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useState(COOLDOWN_S); // a code was just sent on sign-up

  // Same rule as Login/Register: no way back to browsing until the email is verified.
  useFocusEffect(useCallback(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => true);
    return () => sub.remove();
  }, []));

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  async function submit(value = code) {
    const invalid = validateCode(value);
    if (invalid) return setError(invalid);
    setBusy(true);
    setError(null);
    try {
      setUser(await api.verifyEmail(value)); // root navigator then shows the app
    } catch (e) {
      setError(e instanceof ApiError ? e.userMessage : 'Something went wrong.');
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    setError(null);
    try {
      await api.resendVerification();
      setNotice('A new code is on its way.');
      setCooldown(COOLDOWN_S);
    } catch (e) {
      if (e instanceof ApiError && e.code === 'already_verified') {
        setUser(await api.me());
      } else {
        setError(e instanceof ApiError ? e.userMessage : 'Something went wrong.');
      }
    }
  }

  return (
    <FormScreen>
      <AppText variant="title">Verify your email</AppText>
      <AppText variant="caption">We sent a 6-digit code to {user?.email}. It expires in 10 minutes.</AppText>
      <TextField label="Verification code" value={code} keyboardType="number-pad" autoComplete="one-time-code"
        textContentType="oneTimeCode" maxLength={6} error={error}
        onChangeText={(t) => {
          const digits = t.replace(/\D/g, '').slice(0, 6);
          setCode(digits);
          if (digits.length === 6) void submit(digits);
        }} />
      {notice && !error && <AppText variant="caption">{notice}</AppText>}
      <Button title="VERIFY" onPress={() => submit()} loading={busy} />
      <Button title={cooldown > 0 ? `Resend code in ${cooldown}s` : 'Resend code'} variant="ghost"
        disabled={cooldown > 0} onPress={resend} />
      <Button title="Use a different account" variant="ghost" onPress={signOut} />
    </FormScreen>
  );
}
