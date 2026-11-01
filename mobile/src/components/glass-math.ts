/**
 * Pure geometry & motion maths for the water glass. No React / native imports, so it runs on the
 * UI thread (every function is a Reanimated worklet) and in plain Node unit tests (tests/).
 */

export type GlassGeometry = {
  aspect: number; // width / height
  baseRatio: number; // base width / rim width
  rimRadiusRatio: number;
  baseRadiusRatio: number;
  markerRatio: number;
  maxFill: number;
};

type Pt = [number, number];

export function clamp(x: number, lo: number, hi: number): number {
  'worklet';
  return Math.min(Math.max(x, lo), hi);
}

/** Fraction of the glass height that is water: min(total / goal, 1) × maxFill. */
export function fillFraction(totalMl: number, goalMl: number, maxFill: number): number {
  'worklet';
  if (!(goalMl > 0) || !(totalMl > 0)) return 0;
  return clamp(totalMl / goalMl, 0, 1) * maxFill;
}

/** y coordinate (top-left origin) of the resting water surface. */
export function surfaceY(height: number, fill: number): number {
  'worklet';
  return height * (1 - clamp(fill, 0, 1));
}

/** Polygon path with per-corner rounding (quadratic curves at each vertex). */
export function roundedPolygon(points: Pt[], radii: number[]): string {
  const n = points.length;
  let d = '';
  for (let i = 0; i < n; i++) {
    const prev = points[(i - 1 + n) % n];
    const cur = points[i];
    const next = points[(i + 1) % n];
    const toward = (a: Pt, b: Pt, r: number): Pt => {
      const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
      const t = Math.min(r / len, 0.5);
      return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
    };
    const start = toward(cur, prev, radii[i]);
    const end = toward(cur, next, radii[i]);
    d += `${i === 0 ? 'M' : 'L'}${start[0]},${start[1]} Q${cur[0]},${cur[1]} ${end[0]},${end[1]} `;
  }
  return d + 'Z';
}

/** Tapered tumbler silhouette: full-width rim, narrower rounded base. */
export function glassPath(w: number, h: number, g: GlassGeometry): string {
  const inset = (w * (1 - g.baseRatio)) / 2;
  const rim = w * g.rimRadiusRatio;
  const base = w * g.baseRadiusRatio * 2; // quadratic corners need ~2x the radius to look round
  return roundedPolygon([[0, 0], [w, 0], [w - inset, h], [inset, h]], [rim, rim, base, base]);
}

/** Inner horizontal extent [left, right] of the glass at height y (sides are straight lines). */
export function innerSpanAt(y: number, w: number, h: number, baseRatio: number): [number, number] {
  'worklet';
  const inset = ((w * (1 - baseRatio)) / 2) * clamp(y / h, 0, 1);
  return [inset, w - inset];
}

/**
 * Water body with a moving surface: two summed sines (a long swell plus a faster ripple) so the
 * motion never looks like a single rigid wave. `phase` is in radians and advances continuously.
 * The body extends past the glass edges; the glass clip path trims it.
 */
export function wavePath(w: number, h: number, surface: number, amplitude: number, phase: number, steps = 28): string {
  'worklet';
  let d = `M0,${h} L0,${(surface + Math.sin(phase) * amplitude).toFixed(2)}`;
  for (let i = 1; i <= steps; i++) {
    const u = i / steps;
    const y = surface
      + Math.sin(u * Math.PI * 2 + phase) * amplitude
      + Math.sin(u * Math.PI * 5 - phase * 1.7) * amplitude * 0.35;
    d += ` L${(w * u).toFixed(2)},${y.toFixed(2)}`;
  }
  return `${d} L${w},${h} Z`;
}

/**
 * A bubble's position along its rise. `t` in [0, 1) is its own looping clock. It starts at the base,
 * rises to just under the surface and fades out before reaching it (per the design reference).
 */
export function bubbleAt(t: number, baseY: number, surface: number, radius: number): { cy: number; opacity: number } {
  'worklet';
  const top = surface + radius * 3; // never pops through the surface
  if (top >= baseY - radius) return { cy: baseY, opacity: 0 }; // too little water for bubbles
  const p = clamp(t, 0, 1);
  const cy = baseY - (baseY - top) * p;
  const fadeIn = clamp(p / 0.15, 0, 1);
  const fadeOut = clamp((1 - p) / 0.35, 0, 1);
  return { cy, opacity: 0.9 * Math.min(fadeIn, fadeOut) };
}

/** Ease-out cubic count-up from `from` to `to`, `t` in [0, 1]. Whole numbers only. */
export function countAt(from: number, to: number, t: number): number {
  'worklet';
  const e = 1 - Math.pow(1 - clamp(t, 0, 1), 3);
  return Math.round(from + (to - from) * e);
}
