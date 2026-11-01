/**
 * GPS maths for the live workout display. Mirrors backend/app/services/geo.py so the number on screen
 * matches what the server will compute — but the server's figure is the one that's saved.
 * Pure TypeScript (no React Native imports) so it runs in Node unit tests.
 */

export const EARTH_RADIUS_M = 6_371_008.8;
export const MAX_ACCURACY_M = 35;
export const MIN_STEP_M = 3;
export const MAX_SPEED_MPS: Record<string, number> = { walking: 3.5, jogging: 6, running: 10 };

export type Fix = {
  seq: number;
  segment: number;
  t: number; // epoch ms
  lat: number;
  lon: number;
  accuracy?: number | null;
};

export function haversineM(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const rad = Math.PI / 180;
  const p1 = lat1 * rad;
  const p2 = lat2 * rad;
  const dp = p2 - p1;
  const dl = (lon2 - lon1) * rad;
  const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(a)));
}

/**
 * Incremental filter: feed fixes in order; returns the metres this fix adds (0 if rejected) and the
 * new "last kept" fix. Same rules as the server: accuracy, impossible speed, jitter, no bridging pauses.
 */
export function step(last: Fix | null, f: Fix, activity: string): { added: number; last: Fix | null; accepted: boolean } {
  if (last && last.segment !== f.segment) last = null;
  if (f.accuracy != null && f.accuracy > MAX_ACCURACY_M) return { added: 0, last, accepted: false };
  if (!last) return { added: 0, last: f, accepted: true };
  const dt = (f.t - last.t) / 1000;
  const d = haversineM(last.lat, last.lon, f.lat, f.lon);
  if (dt <= 0 || d / dt > (MAX_SPEED_MPS[activity] ?? 10) || d < MIN_STEP_M) return { added: 0, last, accepted: false };
  return { added: d, last: f, accepted: true };
}

export function routeDistanceM(fixes: Fix[], activity: string): number {
  let last: Fix | null = null;
  let total = 0;
  for (const f of [...fixes].sort((a, b) => a.seq - b.seq)) {
    const r = step(last, f, activity);
    total += r.added;
    last = r.last;
  }
  return total;
}

/** "5:42 /km" style pace, or null when there's too little distance to say. */
export function formatPace(distanceM: number, activeS: number): string | null {
  if (distanceM < 10 || activeS <= 0) return null;
  const sPerKm = activeS / (distanceM / 1000);
  if (!Number.isFinite(sPerKm) || sPerKm > 60 * 60) return null;
  const m = Math.floor(sPerKm / 60);
  const s = Math.round(sPerKm % 60);
  return `${s === 60 ? m + 1 : m}:${String(s === 60 ? 0 : s).padStart(2, '0')} /km`;
}

export function formatDuration(totalS: number): string {
  const s = Math.max(0, Math.floor(totalS));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = String(m).padStart(h ? 2 : 1, '0');
  return h ? `${h}:${mm}:${String(sec).padStart(2, '0')}` : `${mm}:${String(sec).padStart(2, '0')}`;
}

export function formatDistance(m: number, units: 'metric' | 'imperial' = 'metric'): string {
  if (units === 'imperial') return `${(m / 1609.344).toFixed(2)} mi`;
  return m < 1000 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(2)} km`;
}

/** Projects a route into a w×h box (equirectangular, fine at workout scale) for an SVG polyline. */
export function projectRoute(points: { lat: number; lon: number; segment: number }[], w: number, h: number, pad = 12) {
  if (points.length < 2) return [];
  const lats = points.map((p) => p.lat);
  const lons = points.map((p) => p.lon);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLon = Math.min(...lons);
  const maxLon = Math.max(...lons);
  const kx = Math.cos(((minLat + maxLat) / 2) * (Math.PI / 180));
  const spanX = Math.max((maxLon - minLon) * kx, 1e-9);
  const spanY = Math.max(maxLat - minLat, 1e-9);
  const scale = Math.min((w - 2 * pad) / spanX, (h - 2 * pad) / spanY);
  const offX = (w - spanX * scale) / 2;
  const offY = (h - spanY * scale) / 2;
  const segments = new Map<number, string[]>();
  for (const p of points) {
    const x = offX + (p.lon - minLon) * kx * scale;
    const y = h - (offY + (p.lat - minLat) * scale); // north up
    const list = segments.get(p.segment) ?? [];
    list.push(`${x.toFixed(1)},${y.toFixed(1)}`);
    segments.set(p.segment, list);
  }
  return [...segments.values()].map((pts) => pts.join(' '));
}
