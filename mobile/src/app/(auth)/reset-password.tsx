import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Alert } from 'react-native';

import { Button } from '@/components/ui/button';
import { FormScreen } from '@/components/ui/screen';
import { AppText } from '@/components/ui/text';
import { TextField } from '@/components/ui/text-field';
import { api, ApiError } from '@/lib/api';
import { validateCode, validatePassword } from '@/lib/validation';

export default function ResetPassword() {
  const params = useLocalSearchParams<{ email?: string }>();
  const email = params.email ?? '';
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<Record<string, string | null>>({});
  const [busy, setBusy] = useState(false);

  async function submit() {
    const next = { code: validateCode(code), password: validatePassword(password) };
    setErrors(next);
    if (next.code || next.password) return;
    setBusy(true);
    try {
      await api.resetPassword(email, code, password);
      Alert.alert('Password updated', 'Sign in with your new password.');
      router.dismissTo('/sign-in');
    } catch (e) {
      setErrors({ form: e instanceof ApiError ? e.userMessage : 'Something went wrong.' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <FormScreen>
      <AppText variant="title">Check your email</AppText>
      <AppText variant="caption">Enter the code we sent to {email || 'your email'} and choose a new password.</AppText>
      <TextField label="6-digit code" value={code} onChangeText={(t) => setCode(t.replace(/\D/g, '').slice(0, 6))}
        keyboardType="number-pad" autoComplete="one-time-code" textContentType="oneTimeCode" error={errors.code} />
      <TextField label="New password" value={password} onChangeText={setPassword} secureTextEntry
        autoComplete="new-password" textContentType="newPassword" error={errors.password} hint="At least 10 characters."
        onSubmitEditing={submit} />
      {errors.form && <AppText variant="error">{errors.form}</AppText>}
      <Button title="UPDATE PASSWORD" onPress={submit} loading={busy} />
      <Button title="Back" variant="ghost" onPress={() => router.back()} />
    </FormScreen>
  );
}
