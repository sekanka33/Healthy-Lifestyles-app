/**
 * Animated tapered tumbler (geometry from picture/69188.png, see docs/design-reference.md).
 *
 * Motion (all on the UI thread via Reanimated):
 * - the water level springs to min(total / goal, 1) × maxFill;
 * - the surface ripples continuously at low amplitude, with a bigger wave (splash) on each add;
 * - bubbles rise from the base and fade before the surface;
 * - the drop marker rides the surface.
 * With the OS "reduce motion" setting on, the level jumps and the water is still.
 */
import { useEffect, useMemo, useRef } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, {
  cancelAnimation,
  Easing,
  SharedValue,
  useAnimatedProps,
  useAnimatedStyle,
  useDerivedValue,
  useReducedMotion,
  useSharedValue,
  withDelay,
  withRepeat,
  withSequence,
  withSpring,
  withTiming,
} from 'react-native-reanimated';
import Svg, { Circle, ClipPath, Defs, G, Path } from 'react-native-svg';

import { colors, glassGeometry as g } from '@/theme/tokens';

import { bubbleAt, clamp, glassPath, surfaceY, wavePath } from './glass-math';

const AnimatedPath = Animated.createAnimatedComponent(Path);
const AnimatedCircle = Animated.createAnimatedComponent(Circle);

const DROP = 'M12 2.5C12 2.5 5 10.3 5 14.8a7 7 0 0 0 14 0C19 10.3 12 2.5 12 2.5Z';
const RIPPLE_PERIOD_MS = 3200;
const SPLASH_MS = 1200;
const BUBBLES = [
  { x: 0.32, r: 0.024, duration: 3400, delay: 0 },
  { x: 0.6, r: 0.017, duration: 2700, delay: 1100 },
  { x: 0.45, r: 0.013, duration: 3900, delay: 2200 },
];

type Props = {
  width: number;
  /** total / goal. May exceed 1 (the glass simply stays full). */
  progress: number;
};

export function WaterGlass({ width, progress }: Props) {
  const height = width / g.aspect;
  const reduceMotion = useReducedMotion();
  const target = clamp(Number.isFinite(progress) ? progress : 0, 0, 1) * g.maxFill;

  const fill = useSharedValue(target);
  const phase = useSharedValue(0);
  const splash = useSharedValue(0);
  const previous = useRef(target);

  // Level: spring toward the target; a rise also kicks a splash wave.
  useEffect(() => {
    const rose = target > previous.current + 1e-4;
    previous.current = target;
    if (reduceMotion) {
      fill.value = target;
      return;
    }
    fill.value = withSpring(target, { damping: 16, stiffness: 70, mass: 1 });
    if (rose) {
      splash.value = withSequence(withTiming(1, { duration: 120 }), withTiming(0, { duration: SPLASH_MS, easing: Easing.out(Easing.quad) }));
    }
  }, [target, reduceMotion, fill, splash]);

  // Continuous ripple clock (radians).
  useEffect(() => {
    if (reduceMotion) {
      cancelAnimation(phase);
      phase.value = 0;
      return;
    }
    phase.value = 0;
    phase.value = withRepeat(withTiming(Math.PI * 2, { duration: RIPPLE_PERIOD_MS, easing: Easing.linear }), -1, false);
    return () => cancelAnimation(phase);
  }, [reduceMotion, phase]);

  const surface = useDerivedValue(() => surfaceY(height, fill.value));
  const restAmp = Math.min(3.5, height * 0.008);
  const splashAmp = Math.min(12, height * 0.03);

  const waterProps = useAnimatedProps(() => {
    const amp = reduceMotion ? 0 : restAmp + splash.value * splashAmp;
    // Keep an empty glass empty: no sliver of wave peeking above the base.
    const visibleAmp = Math.min(amp, (height - surface.value) * 0.5);
    return { d: wavePath(width, height, surface.value, visibleAmp, phase.value) };
  });

  const marker = width * g.markerRatio;
  const markerStyle = useAnimatedStyle(() => {
    const bob = reduceMotion ? 0 : Math.sin(phase.value) * restAmp * 0.8 + splash.value * splashAmp * -0.6;
    // Sit on the surface; when (nearly) empty rest on the base instead of sinking out of the glass.
    const y = Math.min(surface.value + bob, height - marker * 0.6) - marker / 2;
    return { transform: [{ translateY: y }] };
  });

  const outline = useMemo(() => glassPath(width, height, g), [width, height]);
  const percent = Math.round(clamp(progress, 0, 1) * 100);

  return (
    <View style={{ width, height }} accessible accessibilityRole="image" accessibilityLabel={`Glass ${percent} percent full`}>
      <Svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <Defs>
          <ClipPath id="glassClip">
            <Path d={outline} />
          </ClipPath>
        </Defs>
        <Path d={outline} fill={colors.glassBody} />
        <G clipPath="url(#glassClip)">
          <AnimatedPath animatedProps={waterProps} fill={colors.water} />
          {!reduceMotion && BUBBLES.map((b, i) => (
            <Bubble key={i} {...b} width={width} height={height} surface={surface} />
          ))}
        </G>
      </Svg>
      <Animated.View pointerEvents="none" style={[styles.marker, { width: marker, height: marker, left: width / 2 - marker / 2 }, markerStyle]}>
        <Svg width={marker} height={marker} viewBox="0 0 24 24">
          <Circle cx={12} cy={12} r={12} fill={colors.waterMarker} />
          <Path d={DROP} fill={colors.navy} transform="translate(6 5.5) scale(0.5)" />
        </Svg>
      </Animated.View>
    </View>
  );
}

function Bubble({ x, r, duration, delay, width, height, surface }: (typeof BUBBLES)[number] & {
  width: number;
  height: number;
  surface: SharedValue<number>;
}) {
  const t = useSharedValue(0);
  useEffect(() => {
    t.value = withDelay(delay, withRepeat(withTiming(1, { duration, easing: Easing.inOut(Easing.sin) }), -1, false));
    return () => cancelAnimation(t);
  }, [t, delay, duration]);

  const radius = width * r;
  const props = useAnimatedProps(() => {
    const { cy, opacity } = bubbleAt(t.value, height * 0.95, surface.value, radius);
    return { cy, opacity };
  });
  return <AnimatedCircle cx={width * x} cy={height * 0.95} r={radius} opacity={0} fill={colors.waterBubble} animatedProps={props} />;
}

const styles = StyleSheet.create({
  marker: { position: 'absolute', top: 0 },
});
