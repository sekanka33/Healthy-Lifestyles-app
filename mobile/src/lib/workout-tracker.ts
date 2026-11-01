/**
 * GPS workout recording.
 *
 * - Location arrives from a background task (Android foreground service / iOS background location),
 *   so tracking continues with the screen locked. If background location isn't allowed we fall back to
 *   foreground-only updates.
 * - Every fix is appended to a persisted buffer *first*, then uploaded in batches. The server dedups on
 *   (workout, seq) and the workout itself on client_id, so retries and offline gaps are harmless.
 * - Pausing stops GPS; resuming starts a new segment, so the pause never adds distance.
 * - The distance shown live is a local estimate; the server recomputes it from the raw points.
 *
 * Needs a development build: Expo Go can't run background location tasks.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Crypto from 'expo-crypto';
import * as Location from 'expo-location';
import * as TaskManager from 'expo-task-manager';
import { useSyncExternalStore } from 'react';
import { Platform } from 'react-native';

import { Activity, api, ApiError, Workout, WorkoutPointIn } from './api';
import { Fix, step } from './geo';

export const LOCATION_TASK = 'hl-workout-location';
const KEY = 'hl.workout.active';
const BATCH = 200;
const UPLOAD_EVERY = 40; // points

export type ActiveWorkout = {
  clientId: string;
  serverId: string | null;
  activity: Activity;
  startedAt: number; // epoch ms
  state: 'running' | 'paused' | 'finishing';
  segment: number;
  nextSeq: number;
  pausedMs: number;
  pausedAt: number | null;
  endedAt: number | null;
  pending: WorkoutPointIn[]; // recorded but not yet uploaded
  distanceM: number; // live local estimate
  last: Fix | null;
  lastFixAt: number | null;
  accuracyM: number | null;
  foregroundOnly: boolean;
};

let current: ActiveWorkout | null = null;
// Immutable copy handed to React: `current` is mutated in place, so the UI needs a new reference per change.
let snapshot: ActiveWorkout | null = null;
let loaded = false;
let foregroundWatch: Location.LocationSubscription | null = null;
const listeners = new Set<() => void>();
let chain: Promise<unknown> = Promise.resolve();

/** Serialises every read-modify-write of the buffer (task callbacks and UI actions interleave). */
function locked<T>(fn: () => Promise<T>): Promise<T> {
  const run = chain.then(fn, fn);
  chain = run.catch(() => undefined);
  return run;
}

async function load() {
  if (loaded) return;
  const raw = await AsyncStorage.getItem(KEY).catch(() => null);
  current = raw ? JSON.parse(raw) : null;
  loaded = true;
}

function publish() {
  snapshot = current ? { ...current } : null;
  listeners.forEach((l) => l());
}

async function save() {
  publish();
  if (current) await AsyncStorage.setItem(KEY, JSON.stringify(current)).catch(() => undefined);
  else await AsyncStorage.removeItem(KEY).catch(() => undefined);
}

function ingest(locations: Location.LocationObject[]) {
  return locked(async () => {
    await load();
    const w = current;
    if (!w || w.state !== 'running') return;
    for (const loc of locations) {
      if (loc.timestamp < w.startedAt - 60_000) continue; // stale cached fix from before the start
      const fix: Fix = { seq: w.nextSeq++, segment: w.segment, t: loc.timestamp, lat: loc.coords.latitude,
        lon: loc.coords.longitude, accuracy: loc.coords.accuracy };
      const r = step(w.last, fix, w.activity);
      w.distanceM += r.added;
      w.last = r.last;
      w.lastFixAt = loc.timestamp;
      w.accuracyM = loc.coords.accuracy ?? null;
      w.pending.push({
        seq: fix.seq, segment: fix.segment, recorded_at: new Date(fix.t).toISOString(), lat: fix.lat, lon: fix.lon,
        altitude_m: loc.coords.altitude ?? null, accuracy_m: loc.coords.accuracy ?? null,
        speed_mps: loc.coords.speed != null && loc.coords.speed >= 0 ? loc.coords.speed : null,
      });
    }
    await save();
  }).then(() => {
    if ((current?.pending.length ?? 0) >= UPLOAD_EVERY) void upload();
  });
}

// Must run at module load (imported from the root layout) so the task exists when the OS wakes the app.
if (Platform.OS !== 'web') {
  TaskManager.defineTask<{ locations: Location.LocationObject[] }>(LOCATION_TASK, async ({ data, error }) => {
    if (error || !data?.locations?.length) return;
    await ingest(data.locations);
  });
}

// ------------------------------------------------------------------ GPS on/off

async function startUpdates(w: ActiveWorkout) {
  const options: Location.LocationTaskOptions = {
    accuracy: Location.Accuracy.BestForNavigation,
    distanceInterval: 5,
    timeInterval: 3000,
    activityType: Location.LocationActivityType.Fitness,
    pausesUpdatesAutomatically: false,
    showsBackgroundLocationIndicator: true,
    foregroundService: {
      notificationTitle: 'Workout in progress',
      notificationBody: 'Healthy Lifestyles is recording your route.',
      notificationColor: '#04C3D5',
    },
  };
  if (!w.foregroundOnly) {
    try {
      await Location.startLocationUpdatesAsync(LOCATION_TASK, options);
      return;
    } catch {
      w.foregroundOnly = true; // background not permitted: keep going while the app is open
    }
  }
  foregroundWatch?.remove();
  foregroundWatch = await Location.watchPositionAsync(
    { accuracy: Location.Accuracy.BestForNavigation, distanceInterval: 5, timeInterval: 3000 },
    (loc) => void ingest([loc]),
  );
}

async function stopUpdates() {
  foregroundWatch?.remove();
  foregroundWatch = null;
  if (Platform.OS === 'web') return;
  if (await Location.hasStartedLocationUpdatesAsync(LOCATION_TASK).catch(() => false)) {
    await Location.stopLocationUpdatesAsync(LOCATION_TASK).catch(() => undefined);
  }
}

// ------------------------------------------------------------------ server sync

async function ensureServerId(): Promise<string> {
  const w = current!;
  if (w.serverId) return w.serverId;
  const created = await api.startWorkout({ client_id: w.clientId, activity_type: w.activity, started_at: new Date(w.startedAt).toISOString() });
  await locked(async () => {
    if (current && current.clientId === w.clientId) {
      current.serverId = created.id;
      await save();
    }
  });
  return created.id;
}

let uploading: Promise<void> | null = null;

/** Uploads buffered points. Failures (offline) leave them buffered for next time. */
export function upload(): Promise<void> {
  if (!uploading) {
    uploading = (async () => {
      await locked(load);
      if (!current) return;
      const id = await ensureServerId();
      for (;;) {
        const batch = current?.pending.slice(0, BATCH) ?? [];
        if (!batch.length) break;
        await api.addWorkoutPoints(id, batch);
        const sent = new Set(batch.map((p) => p.seq));
        await locked(async () => {
          if (current) current.pending = current.pending.filter((p) => !sent.has(p.seq));
          await save();
        });
      }
    })().catch(() => undefined).finally(() => {
      uploading = null;
    });
  }
  return uploading;
}

// ------------------------------------------------------------------ public API

export class LocationPermissionError extends Error {}

export async function startWorkout(activity: Activity): Promise<void> {
  if (Platform.OS === 'web') throw new LocationPermissionError('GPS workouts need the iOS or Android app.');
  const fg = await Location.requestForegroundPermissionsAsync();
  if (!fg.granted) throw new LocationPermissionError('Location access is needed to record your route.');
  const bg = await Location.requestBackgroundPermissionsAsync().catch(() => ({ granted: false }));
  await locked(async () => {
    await load();
    if (current) return; // one workout at a time
    current = {
      clientId: Crypto.randomUUID(), serverId: null, activity, startedAt: Date.now(), state: 'running', segment: 0,
      nextSeq: 0, pausedMs: 0, pausedAt: null, endedAt: null, pending: [], distanceM: 0, last: null,
      lastFixAt: null, accuracyM: null, foregroundOnly: !bg.granted,
    };
    await save();
  });
  await startUpdates(current!);
  await save();
  void ensureServerId().catch(() => undefined); // offline is fine: retried on upload
}

export async function pauseWorkout() {
  await stopUpdates();
  await locked(async () => {
    if (!current || current.state !== 'running') return;
    current.state = 'paused';
    current.pausedAt = Date.now();
    await save();
  });
  void upload();
}

export async function resumeWorkout() {
  await locked(async () => {
    if (!current || current.state !== 'paused') return;
    current.pausedMs += Date.now() - (current.pausedAt ?? Date.now());
    current.pausedAt = null;
    current.segment += 1;
    current.last = null;
    current.state = 'running';
    await save();
  });
  if (current) await startUpdates(current);
}

export function activeSeconds(w: ActiveWorkout, now = Date.now()): number {
  const end = w.endedAt ?? now;
  const pausedNow = w.pausedAt ? end - w.pausedAt : 0;
  return Math.max(0, Math.floor((end - w.startedAt - w.pausedMs - pausedNow) / 1000));
}

/** Stops recording and saves. Throws if the server can't be reached; call `retryPendingFinish` later. */
export async function finishWorkout(): Promise<Workout> {
  await stopUpdates();
  await locked(async () => {
    if (!current) return;
    if (current.state !== 'finishing') {
      current.endedAt = Date.now();
      current.state = 'finishing';
    }
    await save();
  });
  return completeFinish();
}

async function completeFinish(): Promise<Workout> {
  const w = current;
  if (!w || w.state !== 'finishing') throw new Error('No workout to finish.');
  await upload();
  if (current?.pending.length) throw new ApiError(0, 'network_error', 'Saved on this phone. It will upload when you are back online.');
  const id = await ensureServerId();
  const saved = await api.finishWorkout(id, { ended_at: new Date(w.endedAt!).toISOString(), active_duration_s: activeSeconds(w) });
  await locked(async () => {
    current = null;
    await save();
  });
  return saved;
}

/** Call on launch / when the Fitness tab opens: uploads, retries a pending finish, revives GPS. */
export async function resumePendingWork(): Promise<Workout | null> {
  await locked(load);
  if (!current) return null;
  if (current.state === 'finishing') return completeFinish().catch(() => null);
  if (current.state === 'running' && Platform.OS !== 'web'
      && !(await Location.hasStartedLocationUpdatesAsync(LOCATION_TASK).catch(() => false)) && !foregroundWatch) {
    await startUpdates(current).catch(() => undefined);
  }
  void upload();
  return null;
}

export async function discardWorkout() {
  await stopUpdates();
  const id = current?.serverId;
  await locked(async () => {
    current = null;
    await save();
  });
  if (id) await api.discardWorkout(id).catch(() => undefined);
}

/** Sign-out: stop GPS and drop any local recording (it belongs to the previous account). */
export async function clearActiveWorkout() {
  await stopUpdates();
  await locked(async () => {
    current = null;
    loaded = true;
    await save();
  });
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useActiveWorkout(): ActiveWorkout | null {
  return useSyncExternalStore(subscribe, () => snapshot, () => snapshot);
}

export async function loadActiveWorkout() {
  await locked(load);
  publish();
}
