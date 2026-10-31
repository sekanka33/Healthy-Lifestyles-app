/**
 * Design tokens sampled from picture/69188.png (see docs/design-reference.md).
 * Every screen must use these — never ad-hoc colours — so the product stays consistent.
 */
export const colors = {
  background: '#FEFEFE',
  surface: '#FFFFFF',

  glassBody: '#E8ECEC',
  water: '#04C4D1',
  waterBubble: '#16CDD8',
  waterHighlight: '#3FD3DD',
  waterMarker: '#C6FAFD',

  navy: '#0B1E37',
  navySoft: '#293555',
  navyMuted: '#202D48',
  textMuted: '#6B7489',

  chip: '#EEF0F2',
  chipSelected: '#D2FBFD',

  primary: '#04C3D5',
  primaryEnd: '#02BED6',
  primaryGlow: 'rgba(4, 196, 209, 0.35)',
  onPrimary: '#FFFFFF',

  accentSoft: '#D2FBFD',
  accentWash: '#F4FEFE',
  accentIcon: '#09CFDD',

  tabActive: '#06AAD6',
  tabIndicator: '#0499D2',

  danger: '#D64545',
  border: '#E6E9EE',
} as const;

export const radius = {
  sm: 10,
  md: 16,
  lg: 24,
  pill: 999,
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
} as const;

/** Glass silhouette proportions measured from the reference image. */
export const glassGeometry = {
  aspect: 0.66, // width / height
  baseRatio: 0.67, // base width / rim width
  rimRadiusRatio: 0.015,
  baseRadiusRatio: 0.09,
  markerRatio: 0.19, // marker circle diameter / glass width
  maxFill: 0.94, // water never reaches the rim exactly
} as const;

export const fonts = {
  regular: 'Nunito_600SemiBold',
  bold: 'Nunito_700Bold',
  heavy: 'Nunito_800ExtraBold',
} as const;
