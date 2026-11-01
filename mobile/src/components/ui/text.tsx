import { StyleSheet, Text, TextProps } from 'react-native';

import { colors, fonts } from '@/theme/tokens';

type Variant = 'display' | 'title' | 'heading' | 'body' | 'caption' | 'label' | 'error';

export function AppText({ variant = 'body', style, ...props }: TextProps & { variant?: Variant }) {
  return <Text {...props} style={[styles.base, styles[variant], style]} />;
}

const styles = StyleSheet.create({
  base: { color: colors.navy, fontFamily: fonts.regular },
  display: { fontFamily: fonts.heavy, fontSize: 64, lineHeight: 72 },
  title: { fontFamily: fonts.heavy, fontSize: 30, lineHeight: 38 },
  heading: { fontFamily: fonts.bold, fontSize: 20, lineHeight: 26 },
  body: { fontSize: 16, lineHeight: 22 },
  caption: { fontSize: 15, lineHeight: 20, color: colors.navySoft },
  label: { fontFamily: fonts.bold, fontSize: 14, lineHeight: 18, color: colors.navySoft },
  error: { fontSize: 14, lineHeight: 19, color: colors.danger },
});
