import * as Location from 'expo-location';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Platform, Pressable, StyleSheet, View } from 'react-native';

import { Button } from '@/components/ui/button';
import { FormScreen } from '@/components/ui/screen';
import { AppText } from '@/components/ui/text';
import { TextField } from '@/components/ui/text-field';
import { api, ApiError, Place, WeatherLocation } from '@/lib/api';
import { coarse } from '@/lib/weather-format';
import { colors, fonts } from '@/theme/tokens';

export default function WeatherLocationScreen() {
  const [saved, setSaved] = useState<WeatherLocation | null>(null);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Place[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<'gps' | 'search' | null>(null);

  useEffect(() => {
    api.weatherLocation().then(setSaved).catch(() => undefined);
  }, []);

  async function save(lat: number, lon: number, name: string | null) {
    try {
      await api.setWeatherLocation({ lat: coarse(lat), lon: coarse(lon), name });
      router.back();
    } catch (e) {
      setError(e instanceof ApiError ? e.userMessage : 'Could not save.');
    }
  }

  async function useDevice() {
    setBusy('gps');
    setError(null);
    try {
      const perm = await Location.requestForegroundPermissionsAsync();
      if (!perm.granted) return setError('Location access was declined. You can search for a place instead.');
      // Coarse accuracy is plenty for weather; the value is rounded to ~1 km before it's sent.
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Low });
      await save(pos.coords.latitude, pos.coords.longitude, null);
    } catch {
      setError("Couldn't get your location. Try searching for a place instead.");
    } finally {
      setBusy(null);
    }
  }

  async function search() {
    if (query.trim().length < 2) return setError('Type at least 2 letters.');
    setBusy('search');
    setError(null);
    try {
      const found = await api.searchPlaces(query.trim());
      setResults(found);
      if (!found.length) setError('No places found. Try adding the country, e.g. "Durban, ZA".');
    } catch (e) {
      setError(e instanceof ApiError ? e.userMessage : 'Search failed.');
    } finally {
      setBusy(null);
    }
  }

  async function clear() {
    try {
      await api.clearWeatherLocation();
      router.back();
    } catch (e) {
      setError(e instanceof ApiError ? e.userMessage : 'Could not remove.');
    }
  }

  return (
    <FormScreen>
      <AppText variant="title">Weather location</AppText>
      <AppText variant="caption">
        We store this only to about 1 km and use it just for weather and activity suggestions.
      </AppText>
      {saved?.lat != null && <AppText>Current: {saved.name ?? `${saved.lat}, ${saved.lon}`}</AppText>}

      {Platform.OS !== 'web' && (
        <Button title="Use my current location" onPress={useDevice} loading={busy === 'gps'} disabled={busy !== null} />
      )}
      <TextField label="Or search for a town or city" value={query} onChangeText={setQuery} returnKeyType="search"
        onSubmitEditing={search} placeholder="e.g. Johannesburg" />
      <Button title="Search" variant="secondary" onPress={search} loading={busy === 'search'} disabled={busy !== null} />
      {results?.map((p) => (
        <Pressable key={`${p.lat},${p.lon},${p.name}`} accessibilityRole="button" onPress={() => save(p.lat, p.lon, p.name)}
          style={({ pressed }) => [styles.row, pressed && styles.pressed]}>
          <AppText style={styles.name}>{p.name}</AppText>
        </Pressable>
      ))}
      {error && <AppText variant="error">{error}</AppText>}
      <View style={styles.footer}>
        {saved?.lat != null && <Button title="Remove location" variant="ghost" onPress={clear} />}
        <Button title="Cancel" variant="ghost" onPress={() => router.back()} />
      </View>
    </FormScreen>
  );
}

const styles = StyleSheet.create({
  row: { paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: colors.border },
  name: { fontFamily: fonts.bold },
  pressed: { opacity: 0.6 },
  footer: { marginTop: 8 },
});
