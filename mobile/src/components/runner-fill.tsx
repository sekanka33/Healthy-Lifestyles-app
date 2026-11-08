/**
 * Large runner figure that fills from the feet up as `progress` goes 0 → 1.
 * Same figure as RunIcon (icons.tsx), drawn twice: a muted base and a coloured copy clipped
 * by a rising rectangle. The level eases toward the target; with "reduce motion" on it jumps.
 */
import { useEffect, useRef } from 'react';
import { View } from 'react-native';
import Animated, { Easing, useAnimatedProps, useReducedMotion, useSharedValue, withTiming } from 'react-native-reanimated';
import Svg, { Circle, ClipPath, Defs, G, Path, Rect } from 'react-native-svg';

import { colors } from '@/theme/tokens';

const AnimatedRect = Animated.createAnimatedComponent(Rect);

const BODY = 'M10 8.5l3.2-1.2 2.6 2.4 2.7.8M12.6 8l-1.6 5 3.4 2.6-1.2 5M11 13l-2.7 2.5H5';
const STROKE = 2.6;
// Vertical extent of the figure in the 24×24 viewBox (head top → foot, including stroke caps).
const TOP = 2.3;
const BOTTOM = 21.9;

type Props = {
  size: number;
  /** 0 → empty, 1 → full. Values outside are clamped. */
  progress: number;
  accessibilityLabel?: string;
};

function Figure({ color }: { color: string }) {
  return (
    <>
      <Circle cx="14.5" cy="4.5" r="2.4" fill={color} />
      <Path d={BODY} stroke={color} strokeWidth={STROKE} strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </>
  );
}

export function RunnerFill({ size, progress, accessibilityLabel }: Props) {
  const reduceMotion = useReducedMotion();
  const target = Math.min(Math.max(Number.isFinite(progress) ? progress : 0, 0), 1);
  const level = useSharedValue(target);
  const previous = useRef(target);

  useEffect(() => {
    const dropped = target < previous.current; // e.g. a new lap started: reset instantly, don't drain
    previous.current = target;
    level.value = reduceMotion || dropped ? target : withTiming(target, { duration: 700, easing: Easing.out(Easing.cubic) });
  }, [target, reduceMotion, level]);

  const clipProps = useAnimatedProps(() => {
    const y = BOTTOM - level.value * (BOTTOM - TOP);
    return { y, height: 24 - y };
  });

  return (
    <View style={{ width: size, height: size }} accessible accessibilityRole="image"
      accessibilityLabel={accessibilityLabel ?? `Runner ${Math.round(target * 100)} percent filled`}>
      <Svg width={size} height={size} viewBox="0 0 24 24">
        <Defs>
          <ClipPath id="runnerFillClip">
            <AnimatedRect x={0} width={24} animatedProps={clipProps} />
          </ClipPath>
        </Defs>
        <Figure color={colors.glassBody} />
        <G clipPath="url(#runnerFillClip)">
          <Figure color={colors.primary} />
        </G>
      </Svg>
    </View>
  );
}
