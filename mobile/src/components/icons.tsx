import Svg, { Circle, Path, Rect } from 'react-native-svg';

type P = { size?: number; color: string };

export function DropIcon({ size = 24, color }: P) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      <Path d="M12 2.5C12 2.5 5 10.3 5 14.8a7 7 0 0 0 14 0C19 10.3 12 2.5 12 2.5Z" fill={color} />
    </Svg>
  );
}

export function ChartIcon({ size = 24, color }: P) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      <Rect x="4" y="11" width="4" height="9" rx="1.5" fill={color} />
      <Rect x="10" y="5" width="4" height="15" rx="1.5" fill={color} />
      <Rect x="16" y="8" width="4" height="12" rx="1.5" fill={color} />
    </Svg>
  );
}

export function PersonIcon({ size = 24, color }: P) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      <Circle cx="12" cy="8" r="4" fill={color} />
      <Path d="M4 20.5c0-4 3.6-6.5 8-6.5s8 2.5 8 6.5c0 .5-.4.5-.8.5H4.8c-.4 0-.8 0-.8-.5Z" fill={color} />
    </Svg>
  );
}

export function UndoIcon({ size = 22, color }: P) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      <Path d="M9 7H4V2" stroke={color} strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" fill="none" />
      <Path d="M4.5 7.2A8 8 0 1 1 4 13" stroke={color} strokeWidth={2.4} strokeLinecap="round" fill="none" />
    </Svg>
  );
}

export function PillIcon({ size = 24, color }: P) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      <Path d="M8.5 20.5a5 5 0 0 1-3.5-8.5l7-7a5 5 0 0 1 7 7l-7 7a5 5 0 0 1-3.5 1.5Z" fill={color} />
      <Path d="M8.6 8.4l7 7" stroke="#FFFFFF" strokeWidth={1.8} strokeLinecap="round" />
    </Svg>
  );
}

export function RunIcon({ size = 24, color }: P) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      <Circle cx="14.5" cy="4.5" r="2.2" fill={color} />
      <Path d="M10 8.5l3.2-1.2 2.6 2.4 2.7.8M12.6 8l-1.6 5 3.4 2.6-1.2 5M11 13l-2.7 2.5H5"
        stroke={color} strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </Svg>
  );
}
