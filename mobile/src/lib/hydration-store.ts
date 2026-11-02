/**
 * Offline-first hydration state.
 *
 * Every tap gets a device-generated UUID (`client_id`) and is appended to a persisted queue
 * *before* any network call. The queue is flushed in order; the server's UNIQUE(user, client_id)
 * makes retries and replays harmless, so a flaky connection can never double-count water.
 *
 * What the UI shows = last server snapshot for today + queued adds − queued deletes.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Crypto from 'expo-crypto';
import { useSyncExternalStore } from 'react';

import { api, ApiError, DayDetail, HydrationEntry } from './api';

const SNAPSHOT_KEY = 'hl.hydration.snapshot';
const QUEUE_KEY = 'hl.hydration.queue';

type AddOp = { kind: 'add'; client_id: string; volume_ml: number; consumed_at: string };
type DeleteOp = { kind: 'delete'; client_id: string };
type Op = AddOp | DeleteOp;

export type ViewEntry = { client_id: string; volume_ml: number; consumed_at: string; pending: boolean };

export type HydrationView = {
  ready: boolean;
  date: string; // local YYYY-MM-DD in the user's zone
  totalMl: number;
  goalMl: number;
  entries: ViewEntry[]; // newest first
  pendingCount: number;
  syncing: boolean;
  lastError: string | null;
};

let snapshot: DayDetail | null = null;
let queue: Op[] = [];
let timeZone = 'UTC';
let loaded = false;
let syncing = false;
let lastError: string | null = null;
let view: HydrationView = emptyView();
const listeners = new Set<() => void>();

function emptyView(): HydrationView {
  return { ready: false, date: '', totalMl: 0, goalMl: 2000, entries: [], pendingCount: 0, syncing: false, lastError: null };
}

/** Local calendar date of `d` in an IANA zone, as YYYY-MM-DD. */
export function localDate(d: Date, tz: string): string {
  try {
    return new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit' }).format(d);
  } catch {
    return d.toISOString().slice(0, 10);
  }
}

function recompute() {
  const today = localDate(new Date(), timeZone);
  const fresh = snapshot && snapshot.date === today;
  const deleted = new Set(queue.filter((o) => o.kind === 'delete').map((o) => o.client_id));
  const entries: ViewEntry[] = [];
  for (const e of fresh ? snapshot!.entries : []) {
    if (!e.deleted && !deleted.has(e.client_id)) entries.push({ ...pick(e), pending: false });
  }
  const known = new Set(entries.map((e) => e.client_id));
  for (const o of queue) {
    if (o.kind === 'add' && !known.has(o.client_id) && !deleted.has(o.client_id)
        && localDate(new Date(o.consumed_at), timeZone) === today) {
      entries.push({ client_id: o.client_id, volume_ml: o.volume_ml, consumed_at: o.consumed_at, pending: true });
    }
  }
  entries.sort((a, b) => b.consumed_at.localeCompare(a.consumed_at));
  view = {
    ready: loaded,
    date: today,
    totalMl: entries.reduce((s, e) => s + e.volume_ml, 0),
    goalMl: snapshot?.goal_ml ?? 2000,
    entries,
    pendingCount: queue.length,
    syncing,
    lastError,
  };
  listeners.forEach((l) => l());
}

function pick(e: HydrationEntry) {
  return { client_id: e.client_id, volume_ml: e.volume_ml, consumed_at: e.consumed_at };
}

async function persist() {
  await AsyncStorage.multiSet([
    [QUEUE_KEY, JSON.stringify(queue)],
    [SNAPSHOT_KEY, JSON.stringify(snapshot)],
  ]).catch(() => undefined);
}

// ------------------------------------------------------------------ public API

/** Restores the persisted queue once. Must run before anything writes, or unsynced taps would be lost. */
async function ensureLoaded() {
  if (loaded) return;
  const [[, q], [, s]] = await AsyncStorage.multiGet([QUEUE_KEY, SNAPSHOT_KEY]).catch(() => [[QUEUE_KEY, null], [SNAPSHOT_KEY, null]] as [string, string | null][]);
  queue = [...(q ? JSON.parse(q) : []), ...queue];
  snapshot = s ? JSON.parse(s) : snapshot;
  loaded = true;
}

export async function initHydration(tz: string) {
  timeZone = tz;
  await ensureLoaded();
  recompute();
  await sync();
}

export function setHydrationTimeZone(tz: string) {
  if (tz !== timeZone) {
    timeZone = tz;
    recompute();
  }
}

export async function addWater(volumeMl: number) {
  await ensureLoaded(); // may be called from other screens before the Water tab has opened
  queue.push({ kind: 'add', client_id: Crypto.randomUUID(), volume_ml: volumeMl, consumed_at: new Date().toISOString() });
  recompute();
  await persist();
  void sync();
}

/** Removes the most recent entry. Unsynced adds are simply dropped from the queue. */
export async function undoLast(): Promise<ViewEntry | null> {
  const last = view.entries[0];
  if (!last) return null;
  const idx = queue.findIndex((o) => o.kind === 'add' && o.client_id === last.client_id);
  if (idx >= 0) queue.splice(idx, 1);
  else queue.push({ kind: 'delete', client_id: last.client_id });
  recompute();
  await persist();
  void sync();
  return last;
}

let syncPromise: Promise<void> | null = null;

/** Flushes the queue in order, then refreshes today's snapshot. Safe to call often. */
export function sync(): Promise<void> {
  if (!loaded) return Promise.resolve(); // initHydration() must restore the persisted queue first
  if (!syncPromise) {
    syncPromise = doSync().finally(() => {
      syncPromise = null;
    });
  }
  return syncPromise;
}

async function doSync() {
  syncing = true;
  recompute();
  let dropped: string | null = null;
  try {
    while (queue.length) {
      const op = queue[0];
      try {
        if (op.kind === 'add') await api.addEntry({ client_id: op.client_id, volume_ml: op.volume_ml, consumed_at: op.consumed_at });
        else await api.deleteEntry(op.client_id);
      } catch (e) {
        if (!(e instanceof ApiError) || e.isNetwork || e.status === 401 || e.status === 429 || e.status >= 500) throw e;
        // 404 on delete = it never reached the server; other 4xx can never succeed. Drop it.
        if (!(op.kind === 'delete' && e.status === 404)) dropped = `An entry was rejected: ${e.userMessage}`;
      }
      queue.shift();
      await persist();
    }
    snapshot = await api.today();
    lastError = dropped;
    await persist();
  } catch (e) {
    lastError = e instanceof ApiError ? (e.isNetwork ? 'Offline — will sync when you reconnect.' : e.userMessage) : 'Sync failed.';
  } finally {
    syncing = false;
    recompute();
  }
}

export async function clearHydrationCache() {
  queue = [];
  snapshot = null;
  loaded = false;
  lastError = null;
  await AsyncStorage.multiRemove([QUEUE_KEY, SNAPSHOT_KEY]).catch(() => undefined);
  view = emptyView();
  listeners.forEach((l) => l());
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

/** Whether today's goal is met, as far as this device knows. False until today's data has loaded. */
export function hydrationGoalMet(): boolean {
  return view.ready && view.date === localDate(new Date(), timeZone) && view.totalMl >= view.goalMl;
}

export function useHydration(): HydrationView {
  return useSyncExternalStore(subscribe, () => view, () => view);
}
