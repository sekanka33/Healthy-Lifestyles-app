import { router } from 'expo-router';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { FormScreen } from '@/components/ui/screen';
import { AppText } from '@/components/ui/text';
import { TextField } from '@/components/ui/text-field';
import { api, ApiError, saveTokens } from '@/lib/api';
import { validatePassword } from '@/lib/validation';

export default function ChangePassword() {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [errors, setErrors] = useState<Record<string, string | null>>({});
  const [busy, setBusy] = useState(false);

  async function submit() {
    const e = { current: current ? null : 'Enter your current password.', next: validatePassword(next) };
    setErrors(e);
    if (e.current || e.next) return;
    setBusy(true);
    try {
      // The server signs out every other device and returns fresh tokens for this one.
      await saveTokens(await api.changePassword(current, next));
      router.back();
    } catch (err) {
      setErrors({ form: err instanceof ApiError ? err.userMessage : 'Something went wrong.' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <FormScreen>
      <AppText variant="title">Change password</AppText>
      <AppText variant="caption">You&apos;ll stay signed in here; other devices will be signed out.</AppText>
      <TextField label="Current password" value={current} onChangeText={setCurrent} secureTextEntry
        autoComplete="current-password" textContentType="password" error={errors.current} />
      <TextField label="New password" value={next} onChangeText={setNext} secureTextEntry autoComplete="new-password"
        textContentType="newPassword" error={errors.next} hint="At least 10 characters." onSubmitEditing={submit} />
      {errors.form && <AppText variant="error">{errors.form}</AppText>}
      <Button title="UPDATE PASSWORD" onPress={submit} loading={busy} />
      <Button title="Cancel" variant="ghost" onPress={() => router.back()} />
    </FormScreen>
  );
}
