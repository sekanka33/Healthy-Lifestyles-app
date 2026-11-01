import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';

import { api, ApiError, CurrentWeather, Forecast } from '@/lib/api';

export type WeatherState =
  | { status: 'idle' | 'loading' }
  | { status: 'no_location' }
  | { status: 'error'; message: string }
  | { status: 'ready'; current: CurrentWeather; forecast: Forecast | null };

/** Loads current weather (and the forecast for Premium) whenever the screen gains focus. */
export function useWeather({ enabled, withForecast }: { enabled: boolean; withForecast: boolean }) {
  const [state, setState] = useState<WeatherState>({ status: 'idle' });

  const reload = useCallback(async () => {
    if (!enabled) return;
    setState((s) => (s.status === 'ready' ? s : { status: 'loading' }));
    try {
      const [current, forecast] = await Promise.all([
        api.currentWeather(),
        withForecast ? api.forecast(24).catch(() => null) : Promise.resolve(null),
      ]);
      setState({ status: 'ready', current, forecast });
    } catch (e) {
      if (e instanceof ApiError && e.code === 'no_location') setState({ status: 'no_location' });
      else setState({ status: 'error', message: e instanceof ApiError ? e.userMessage : 'Weather is unavailable.' });
    }
  }, [enabled, withForecast]);

  useFocusEffect(useCallback(() => void reload(), [reload]));
  return { state, reload };
}
