/** Pure weather formatting (no React Native imports — unit-tested in Node). */

export function formatTemp(c: number | null | undefined, units: 'metric' | 'imperial' = 'metric'): string {
  if (c == null || !Number.isFinite(c)) return '—';
  return units === 'imperial' ? `${Math.round((c * 9) / 5 + 32)}°F` : `${Math.round(c)}°C`;
}

export function formatWind(mps: number | null | undefined, units: 'metric' | 'imperial' = 'metric'): string {
  if (mps == null || !Number.isFinite(mps)) return '—';
  return units === 'imperial' ? `${Math.round(mps * 2.23694)} mph` : `${Math.round(mps * 3.6)} km/h`;
}

/** OpenWeather condition id → a simple glyph (system emoji; no icon font needed). */
export function conditionGlyph(code: number, isDay = true): string {
  if (code >= 200 && code < 300) return '⛈️';
  if (code >= 300 && code < 600) return '🌧️';
  if (code >= 600 && code < 700) return '❄️';
  if (code >= 700 && code < 800) return '🌫️';
  if (code === 800) return isDay ? '☀️' : '🌙';
  if (code === 801) return isDay ? '🌤️' : '☁️';
  return '☁️';
}

export function outdoorVerdict(label: 'good' | 'fair' | 'poor'): string {
  return label === 'good' ? 'Good for a walk or run' : label === 'fair' ? 'OK outside — plan around it' : 'Better to exercise indoors';
}

export function capitalise(s: string): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

/** Round a coordinate to ~1 km before it leaves the device (the server rounds again). */
export function coarse(value: number): number {
  return Math.round(value * 100) / 100;
}
