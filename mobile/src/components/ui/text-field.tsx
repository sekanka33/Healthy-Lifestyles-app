import { Ref, useState } from 'react';
import { StyleSheet, TextInput, TextInputInstance, TextInputProps, View } from 'react-native';

import { colors, fonts, radius } from '@/theme/tokens';

import { AppText } from './text';

type Props = TextInputProps & { label: string; error?: string | null; hint?: string; ref?: Ref<TextInputInstance> };

export function TextField({ label, error, hint, style, ref, ...props }: Props) {
  const [focused, setFocused] = useState(false);
  return (
    <View style={styles.wrap}>
      <AppText variant="label">{label}</AppText>
      <TextInput
        {...props}
        ref={ref}
        accessibilityLabel={label}
        placeholderTextColor={colors.textMuted}
        onFocus={(e) => {
          setFocused(true);
          props.onFocus?.(e);
        }}
        onBlur={(e) => {
          setFocused(false);
          props.onBlur?.(e);
        }}
        style={[styles.input, focused && styles.focused, !!error && styles.invalid, style]}
      />
      {error ? <AppText variant="error">{error}</AppText> : hint ? <AppText variant="caption" style={styles.hint}>{hint}</AppText> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 6 },
  input: {
    minHeight: 52,
    borderRadius: radius.md,
    backgroundColor: colors.chip,
    paddingHorizontal: 16,
    fontFamily: fonts.bold,
    fontSize: 16,
    color: colors.navy,
    borderWidth: 2,
    borderColor: 'transparent',
  },
  focused: { borderColor: colors.primary, backgroundColor: colors.surface },
  invalid: { borderColor: colors.danger },
  hint: { fontSize: 13 },
});
