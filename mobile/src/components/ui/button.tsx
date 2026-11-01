import { ReactNode } from 'react';
import { ActivityIndicator, Pressable, PressableProps, StyleSheet, ViewStyle } from 'react-native';

import { colors, fonts, radius } from '@/theme/tokens';

import { AppText } from './text';

type Props = Omit<PressableProps, 'children' | 'style'> & {
  title: string;
  variant?: 'primary' | 'secondary' | 'ghost';
  loading?: boolean;
  icon?: ReactNode;
  style?: ViewStyle;
};

/** Pill button. Primary matches the "+ WATER" button (cyan, soft glow, scales on press). */
export function Button({ title, variant = 'primary', loading, disabled, icon, style, ...props }: Props) {
  const isDisabled = disabled || loading;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!isDisabled, busy: !!loading }}
      disabled={isDisabled}
      style={({ pressed }) => [
        styles.base,
        styles[variant],
        pressed && { transform: [{ scale: 0.96 }] },
        isDisabled && styles.disabled,
        style,
      ]}
      {...props}>
      {loading ? (
        <ActivityIndicator color={variant === 'primary' ? colors.onPrimary : colors.primary} />
      ) : (
        <>
          {icon}
          <AppText style={[styles.label, variant === 'primary' ? styles.labelPrimary : styles.labelOther]}>{title}</AppText>
        </>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: 54,
    borderRadius: radius.pill,
    paddingHorizontal: 28,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
  },
  primary: {
    backgroundColor: colors.primary,
    shadowColor: colors.water,
    shadowOpacity: 0.35,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 8 },
    elevation: 6,
  },
  secondary: { backgroundColor: colors.accentSoft },
  ghost: { backgroundColor: 'transparent', minHeight: 44 },
  disabled: { opacity: 0.55 },
  label: { fontFamily: fonts.heavy, fontSize: 17, letterSpacing: 0.4 },
  labelPrimary: { color: colors.onPrimary },
  labelOther: { color: colors.tabActive },
});
