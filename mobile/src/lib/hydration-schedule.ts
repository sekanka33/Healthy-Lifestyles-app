/**
 * The pure maths behind hydration reminders: when they fire and how times are read and shown.
 * No React Native imports, so `npm test` can run it directly.
 */

export const DEFAULT_INTERVAL_MINUTES = 90;
export const DEFAULT_QUIET_START = '22:00';
export const DEFAULT_QUIET_END = '07:00';

/** iOS keeps 64 pending notifications per app. Medication reminders hold the other 40. */
export const MAX_DAILY_REMINDERS = 24;

export type Slot = { hour: number; minute: number };

const DAY = 24 * 60;

function toMinutes(clock: string): number {
  const [hour, minute] = clock.split(':').map(Number);
  return hour * 60 + minute;
}

/**
 * The times of day a reminder fires: from the end of quiet hours, every `intervalMinutes`, stopping
 * before quiet hours begin again. Quiet hours may cross midnight. If the waking day holds more than
 * MAX_DAILY_REMINDERS, they are spaced out evenly rather than dropping the evening ones.
 */
export function reminderSlots(intervalMinutes: number, quietStart: string, quietEnd: string): Slot[] {
  const first = toMinutes(quietEnd);
  const waking = (toMinutes(quietStart) - first + DAY) % DAY;
  const step = Math.max(intervalMinutes, Math.ceil(waking / MAX_DAILY_REMINDERS));
  const slots: Slot[] = [];
  for (let offset = 0; offset < waking; offset += step) {
    const at = (first + offset) % DAY;
    slots.push({ hour: Math.floor(at / 60), minute: at % 60 });
  }
  return slots;
}

/** Reads "22:00", "10 pm", "10pm" or "10:00 PM" as 24-hour "HH:MM". Returns null if it isn't a time. */
export function parseClock(input: string): string | null {
  const match = /^(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m?\.?$|^(\d{1,2}):(\d{2})$/i.exec(input.trim());
  if (!match) return null;
  const meridiem = match[3]?.toLowerCase();
  let hour = Number(match[1] ?? match[4]);
  const minute = Number(match[2] ?? match[5] ?? 0);
  if (minute > 59) return null;
  if (meridiem) {
    if (hour < 1 || hour > 12) return null;
    hour = (hour % 12) + (meridiem === 'p' ? 12 : 0);
  } else if (hour > 23) {
    return null;
  }
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
}

/** "22:00" (or the API's "22:00:00") -> "10:00 PM". */
export function formatClock(clock: string): string {
  const [hour, minute] = clock.split(':').map(Number);
  return `${hour % 12 || 12}:${String(minute).padStart(2, '0')} ${hour < 12 ? 'AM' : 'PM'}`;
}

/** 90 -> "1 h 30 min". */
export function formatInterval(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (!hours) return `${rest} min`;
  return rest ? `${hours} h ${rest} min` : `${hours} h`;
}
