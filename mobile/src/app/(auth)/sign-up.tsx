import { router } from 'expo-router';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { FormScreen } from '@/components/ui/screen';
import { AppText } from '@/components/ui/text';
import { TextField } from '@/components/ui/text-field';
import { ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { validateEmail, validatePassword } from '@/lib/validation';

export default function SignUp() {
  const { signUp } = useAuth();
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errors, setErrors] = useState<Record<string, string | null>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    const next = {
      firstName: firstName.trim() ? null : 'Enter your first name.',
      email: validateEmail(email),
      password: validatePassword(password),
      confirm: password === confirm ? null : "Passwords don't match.",
    };
    setErrors(next);
    if (Object.values(next).some(Boolean)) return;
    setBusy(true);
    setFormError(null);
    try {
      await signUp({ email, password, first_name: firstName.trim(), last_name: lastName.trim() || undefined });
      // The root navigator now routes to /verify-email.
    } catch (e) {
      if (e instanceof ApiError && e.code === 'email_taken') setErrors({ email: e.message });
      else setFormError(e instanceof ApiError ? e.userMessage : 'Something went wrong.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <FormScreen>
      <AppText variant="title">Create your account</AppText>
      <AppText variant="caption">Track your water for free. Upgrade any time for more.</AppText>
      <TextField label="First name" value={firstName} onChangeText={setFirstName} autoComplete="given-name"
        textContentType="givenName" error={errors.firstName} />
      <TextField label="Last name (optional)" value={lastName} onChangeText={setLastName} autoComplete="family-name"
        textContentType="familyName" />
      <TextField label="Email" value={email} onChangeText={setEmail} autoCapitalize="none" autoComplete="email"
        keyboardType="email-address" textContentType="emailAddress" error={errors.email} />
      <TextField label="Password" value={password} onChangeText={setPassword} secureTextEntry autoComplete="new-password"
        textContentType="newPassword" error={errors.password} hint="At least 10 characters." />
      <TextField label="Confirm password" value={confirm} onChangeText={setConfirm} secureTextEntry
        autoComplete="new-password" textContentType="newPassword" error={errors.confirm} onSubmitEditing={submit} />
      {formError && <AppText variant="error">{formError}</AppText>}
      <Button title="CREATE ACCOUNT" onPress={submit} loading={busy} />
      <Button title="I already have an account" variant="ghost" onPress={() => router.back()} />
    </FormScreen>
  );
}
