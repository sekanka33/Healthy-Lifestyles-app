import { router } from 'expo-router';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { FormScreen } from '@/components/ui/screen';
import { AppText } from '@/components/ui/text';
import { TextField } from '@/components/ui/text-field';
import { api, ApiError } from '@/lib/api';
import { validateEmail } from '@/lib/validation';

export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    const invalid = validateEmail(email);
    if (invalid) return setError(invalid);
    setBusy(true);
    setError(null);
    try {
      await api.forgotPassword(email.trim());
      router.push({ pathname: '/reset-password', params: { email: email.trim() } });
    } catch (e) {
      setError(e instanceof ApiError ? e.userMessage : 'Something went wrong.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <FormScreen>
      <AppText variant="title">Reset your password</AppText>
      <AppText variant="caption">
        Enter your account email. If it matches an account, we&apos;ll send a 6-digit code.
      </AppText>
      <TextField label="Email" value={email} onChangeText={setEmail} autoCapitalize="none" autoComplete="email"
        keyboardType="email-address" textContentType="emailAddress" error={error} onSubmitEditing={submit} />
      <Button title="SEND CODE" onPress={submit} loading={busy} />
      <Button title="Back to sign in" variant="ghost" onPress={() => router.back()} />
    </FormScreen>
  );
}
