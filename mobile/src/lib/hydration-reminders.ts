/**
 * Hydration reminders as on-device notifications that repeat daily at fixed times of day.
 *
 * Quiet hours hold by construction: nothing is ever scheduled inside them. Repeating triggers keep
 * going if the app isn't opened, and follow the phone's clock when travelling or at a DST change.
 * The cost is that a closed app can't skip a reminder once the goal is met (only an open app can).
 */
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';

import { api } from './api';
import { DEFAULT_QUIET_END, DEFAULT_QUIET_START, reminderSlots } from './hydration-schedule';

const KIND = 'hydration-reminder';
const CHANNEL = 'hydration';

// One at a time, so a save and a foreground refresh can't interleave into duplicate reminders, and a
// sign-out always wins over a refresh that was already running.
let queue: Promise<unknown> = Promise.resolve();
function serial<T>(task: () => Promise<T>): Promise<T> {
  const run = queue.then(task, task);
  queue = run.catch(() => undefined);
  return run;
}

async function cancelAll() {
  const pending = await Notifications.getAllScheduledNotificationsAsync().catch(() => []);
  await Promise.all(pending
    .filter((n) => n.content.data?.kind === KIND)
    .map((n) => Notifications.cancelScheduledNotificationAsync(n.identifier)));
}

export function clearHydrationReminders(): Promise<void> {
  if (Platform.OS === 'web') return Promise.resolve();
  return serial(cancelAll);
}

/** Re-plans the reminders from the saved settings. If they can't be fetched, the current ones stay. */
export function syncHydrationReminders(): Promise<void> {
  if (Platform.OS === 'web') return Promise.resolve();
  return serial(async () => {
    const prefs = await api.notificationPrefs();
    if (!prefs.hydration_reminders_enabled) return cancelAll();
    if (!(await Notifications.getPermissionsAsync()).granted) return;

    const slots = reminderSlots(
      prefs.hydration_reminder_interval_minutes,
      prefs.quiet_hours_start ?? DEFAULT_QUIET_START,
      prefs.quiet_hours_end ?? DEFAULT_QUIET_END,
    );
    if (Platform.OS === 'android') {
      await Notifications.setNotificationChannelAsync(CHANNEL, {
        name: 'Water reminders',
        importance: Notifications.AndroidImportance.DEFAULT,
      });
    }
    await cancelAll();
    for (const { hour, minute } of slots) {
      await Notifications.scheduleNotificationAsync({
        content: {
          title: 'Time for some water 💧',
          body: 'Tap to see your goal and top up your glass.',
          data: { kind: KIND },
        },
        trigger: { type: Notifications.SchedulableTriggerInputTypes.DAILY, hour, minute, channelId: CHANNEL },
      });
    }
  });
}

export function isHydrationReminder(notification: Notifications.Notification): boolean {
  return notification.request.content.data?.kind === KIND;
}

