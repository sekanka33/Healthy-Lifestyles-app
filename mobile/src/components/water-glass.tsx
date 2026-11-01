/**
 * Tapered tumbler from picture/69188.png (geometry in docs/design-reference.md).
 * Phase 3: static fill level. Phase 4 animates the level, surface ripple, splash and bubbles.
 */
import Svg, { Circle, ClipPath, Defs, G, Path } from 'react-native-svg';

import { colors, glassGeometry as g } from '@/theme/tokens';

type Pt = [number, number];

/** Polygon path with per-corner rounding (quadratic curves at each vertex). */
function roundedPolygon(points: Pt[], radii: number[]): string {
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

export function glassPath(w: number, h: number) {
  const inset = (w * (1 - g.baseRatio)) / 2;
  const rim = w * g.rimRadiusRatio;
  const base = w * g.baseRadiusRatio * 2; // quadratic corners need ~2x the radius to look round
  return roundedPolygon([[0, 0], [w, 0], [w - inset, h], [inset, h]], [rim, rim, base, base]);
}

function wavePath(w: number, surfaceY: number, h: number, amp: number) {
  const steps = 24;
  let d = `M0,${surfaceY}`;
  for (let i = 1; i <= steps; i++) {
    const x = (w * i) / steps;
    const y = surfaceY + Math.sin((i / steps) * Math.PI * 2) * amp;
    d += ` L${x.toFixed(2)},${y.toFixed(2)}`;
  }
  return `${d} L${w},${h} L0,${h} Z`;
}

export function WaterGlass({ width, progress }: { width: number; progress: number }) {
  const height = width / g.aspect;
  const fill = Math.max(0, Math.min(progress, 1)) * g.maxFill;
  const surfaceY = height * (1 - fill);
  const marker = width * g.markerRatio;
  const showWater = fill > 0.001;

  return (
    <Svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}
      accessibilityRole="image" accessibilityLabel={`Glass ${Math.round(Math.min(progress, 1) * 100)} percent full`}>
      <Defs>
        <ClipPath id="glass">
          <Path d={glassPath(width, height)} />
        </ClipPath>
      </Defs>
      <Path d={glassPath(width, height)} fill={colors.glassBody} />
      {showWater && (
        <G clipPath="url(#glass)">
          <Path d={wavePath(width, surfaceY, height, Math.min(4, height * 0.008))} fill={colors.water} />
          <Circle cx={width * 0.3} cy={Math.min(height * 0.88, surfaceY + height * 0.3)} r={width * 0.025} fill={colors.waterBubble} />
          <Circle cx={width * 0.62} cy={Math.min(height * 0.8, surfaceY + height * 0.18)} r={width * 0.018} fill={colors.waterBubble} />
        </G>
      )}
      {/* Marker riding the surface (sits on the base when empty). */}
      <G transform={`translate(${width / 2 - marker / 2}, ${Math.min(surfaceY, height - marker * 0.6) - marker / 2})`}>
        <Circle cx={marker / 2} cy={marker / 2} r={marker / 2} fill={colors.waterMarker} />
        <Path
          transform={`translate(${marker * 0.25}, ${marker * 0.22}) scale(${(marker * 0.5) / 24})`}
          d="M12 2.5C12 2.5 5 10.3 5 14.8a7 7 0 0 0 14 0C19 10.3 12 2.5 12 2.5Z"
          fill={colors.navy}
        />
      </G>
    </Svg>
  );
}
