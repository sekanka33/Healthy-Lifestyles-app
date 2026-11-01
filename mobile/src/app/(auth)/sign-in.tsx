import { Link } from 'expo-router';
import { useRef, useState } from 'react';
import { StyleSheet, TextInputInstance, View } from 'react-native';

import { DropIcon } from '@/components/icons';
import { Button } from '@/components/ui/button';
import { FormScreen } from '@/components/ui/screen';
import { AppText } from '@/components/ui/text';
import { TextField } from '@/components/ui/text-field';
import { ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { colors } from '@/theme/tokens';

export default function SignIn() {
  const { signIn } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const passwordRef = useRef<TextInputInstance>(null);

  async function submit() {
    if (!email.trim() || !password) return setError('Enter your email and password.');
    setBusy(true);
    setError(null);
    try {
      await signIn(email, password);
    } catch (e) {
      setError(e instanceof ApiError ? e.userMessage : 'Something went wrong.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <FormScreen>
      <View style={styles.brand}>
        <View style={styles.logo}>
          <DropIcon size={34} color={colors.navy} />
        </View>
        <AppText variant="title">Welcome back</AppText>
        <AppText variant="caption">Sign in to keep your hydration streak going.</AppText>
      </View>

      <TextField label="Email" value={email} onChangeText={setEmail} autoCapitalize="none" autoComplete="email"
        keyboardType="email-address" textContentType="emailAddress" returnKeyType="next"
        onSubmitEditing={() => passwordRef.current?.focus()} />
      <TextField ref={passwordRef} label="Password" value={password} onChangeText={setPassword} secureTextEntry
        autoComplete="current-password" textContentType="password" returnKeyType="go" onSubmitEditing={submit} />
      {error && <AppText variant="error" accessibilityLiveRegion="polite">{error}</AppText>}

      <Button title="SIGN IN" onPress={submit} loading={busy} />
      <Link href="/forgot-password" asChild>
        <Button title="Forgot password?" variant="ghost" />
      </Link>
      <View style={styles.footer}>
        <AppText variant="caption">New here?</AppText>
        <Link href="/sign-up" asChild>
          <Button title="Create an account" variant="ghost" />
        </Link>
      </View>
    </FormScreen>
  );
}

const styles = StyleSheet.create({
  brand: { alignItems: 'center', gap: 8, marginBottom: 12 },
  logo: {
    width: 72, height: 72, borderRadius: 36, backgroundColor: colors.waterMarker,
    alignItems: 'center', justifyContent: 'center', marginBottom: 8,
  },
  footer: { alignItems: 'center', marginTop: 8 },
});
