/**
 * Medication reminders as on-device local notifications (they fire offline, no push server).
 *
 * We schedule individual dose times for the next 7 days, refreshed whenever medications change and
 * when the app comes to the foreground. iOS keeps at most 64 pending notifications per app, so we cap
 * at 60. The text is deliberately generic: medication names never appear on the lock screen.
 */
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';

import { api, Medication } from './api';
import { localDate } from './hydration-store';

const KIND = 'medication-reminder';
const CHANNEL = 'medication';
const HORIZON_DAYS = 7;
const MAX_PENDING = 60;

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

async function ensureChannel() {
  if (Platform.OS !== 'android') return;
  await Notifications.setNotificationChannelAsync(CHANNEL, {
    name: 'Medication reminders',
    importance: Notifications.AndroidImportance.HIGH,
    lockscreenVisibility: Notifications.AndroidNotificationVisibility.PRIVATE,
  });
}

/** Asks for permission only when the user turns reminders on. Returns whether we may notify. */
export async function requestReminderPermission(): Promise<boolean> {
  if (Platform.OS === 'web') return false;
  const current = await Notifications.getPermissionsAsync();
  if (current.granted) return true;
  if (!current.canAskAgain) return false;
  return (await Notifications.requestPermissionsAsync()).granted;
}

export async function clearMedicationReminders(): Promise<void> {
  if (Platform.OS === 'web') return;
  const pending = await Notifications.getAllScheduledNotificationsAsync().catch(() => []);
  await Promise.all(pending
    .filter((n) => n.content.data?.kind === KIND)
    .map((n) => Notifications.cancelScheduledNotificationAsync(n.identifier)));
}

/** Re-plans every reminder from the server's schedule. Safe to call often. */
export async function syncMedicationReminders(timeZone: string, meds?: Medication[]): Promise<void> {
  if (Platform.OS === 'web') return;
  const permission = await Notifications.getPermissionsAsync();
  if (!permission.granted) return;

  const list = meds ?? (await api.medications());
  const remind = new Set(list.filter((m) => m.active && m.reminders_enabled).map((m) => m.id));
  const now = new Date();
  const from = localDate(now, timeZone);
  const to = localDate(new Date(now.getTime() + (HORIZON_DAYS - 1) * 86400000), timeZone);
  const doses = remind.size ? await api.medicationSchedule(from, to) : [];

  await ensureChannel();
  await clearMedicationReminders();
  const upcoming = doses
    .filter((d) => d.status === 'upcoming' && remind.has(d.medication_id) && new Date(d.scheduled_for) > now)
    .slice(0, MAX_PENDING);
  for (const d of upcoming) {
    await Notifications.scheduleNotificationAsync({
      content: {
        title: 'Medication reminder',
        body: "It's time for a scheduled dose. Open the app to log it.",
        data: { kind: KIND, medicationId: d.medication_id, scheduledFor: d.scheduled_for },
      },
      trigger: { type: Notifications.SchedulableTriggerInputTypes.DATE, date: new Date(d.scheduled_for), channelId: CHANNEL },
    });
  }
}

/** True when a tapped notification is one of ours (used to open the Meds tab). */
export function isMedicationReminder(response: Notifications.NotificationResponse): boolean {
  return response.notification.request.content.data?.kind === KIND;
}
