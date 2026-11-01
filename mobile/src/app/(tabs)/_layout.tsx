import { Tabs } from 'expo-router';
import type { BottomTabBarProps } from 'expo-router/tabs';
import { Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ChartIcon, DropIcon, PersonIcon, PillIcon } from '@/components/icons';
import { AppText } from '@/components/ui/text';
import { colors, fonts } from '@/theme/tokens';

const ICONS = { index: DropIcon, history: ChartIcon, medications: PillIcon, profile: PersonIcon } as const;
const LABELS = { index: 'Water', history: 'History', medications: 'Meds', profile: 'Profile' } as const;

/** White bar, large top radius, active tab with a short rounded underline (per the reference). */
function TabBar({ state, navigateToTab }: BottomTabBarProps) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.bar, { paddingBottom: Math.max(insets.bottom, 10) }]}>
      {state.routes.map((route, i) => {
        const focused = state.index === i;
        const name = route.name as keyof typeof ICONS;
        const Icon = ICONS[name];
        const color = focused ? colors.tabActive : colors.navyMuted;
        return (
          <Pressable
            key={route.key}
            accessibilityRole="tab"
            accessibilityState={{ selected: focused }}
            accessibilityLabel={LABELS[name]}
            style={styles.item}
            onPress={() => !focused && navigateToTab(route.key)}>
            <Icon size={24} color={color} />
            <AppText style={[styles.label, { color }]}>{LABELS[name]}</AppText>
            <View style={[styles.indicator, focused && styles.indicatorOn]} />
          </Pressable>
        );
      })}
    </View>
  );
}

export default function TabsLayout() {
  return (
    <Tabs screenOptions={{ headerShown: false, sceneStyle: { backgroundColor: colors.background } }}
      tabBar={(props) => <TabBar {...props} />}>
      <Tabs.Screen name="index" />
      <Tabs.Screen name="history" />
      <Tabs.Screen name="medications" />
      <Tabs.Screen name="profile" />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: 'row',
    backgroundColor: colors.surface,
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    paddingTop: 12,
    shadowColor: colors.navy,
    shadowOpacity: 0.06,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: -4 },
    elevation: 12,
  },
  item: { flex: 1, alignItems: 'center', gap: 3, minHeight: 48 },
  label: { fontFamily: fonts.regular, fontSize: 13 },
  indicator: { width: 22, height: 3, borderRadius: 2, marginTop: 2, backgroundColor: 'transparent' },
  indicatorOn: { backgroundColor: colors.tabIndicator },
});
