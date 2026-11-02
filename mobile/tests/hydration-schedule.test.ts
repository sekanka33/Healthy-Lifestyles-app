/// <reference types="node" />
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { formatClock, formatInterval, MAX_DAILY_REMINDERS, parseClock, reminderSlots } from '../src/lib/hydration-schedule.ts';

const labels = (interval: number, start: string, end: string) =>
  reminderSlots(interval, start, end).map((s) => `${s.hour}:${String(s.minute).padStart(2, '0')}`);

test('default: every 1 h 30 from 7:00 AM, nothing from 10:00 PM', () => {
  assert.deepEqual(labels(90, '22:00', '07:00'),
    ['7:00', '8:30', '10:00', '11:30', '13:00', '14:30', '16:00', '17:30', '19:00', '20:30']);
});

test('a reminder landing exactly on the start of quiet hours is dropped', () => {
  assert.deepEqual(labels(60, '10:00', '08:00'), ['8:00', '9:00']);
});

test('no slot ever falls inside quiet hours, whatever the window', () => {
  const windows = [['22:00', '07:00'], ['23:30', '05:15'], ['01:00', '09:00'], ['00:00', '06:00'], ['13:00', '21:00']];
  for (const [start, end] of windows) {
    for (const interval of [30, 45, 60, 90, 120, 180, 240, 480]) {
      const s = Number(start.slice(0, 2)) * 60 + Number(start.slice(3));
      const e = Number(end.slice(0, 2)) * 60 + Number(end.slice(3));
      for (const slot of reminderSlots(interval, start, end)) {
        const at = slot.hour * 60 + slot.minute;
        const quiet = s < e ? at >= s && at < e : at >= s || at < e;
        assert.equal(quiet, false, `${slot.hour}:${slot.minute} is inside ${start}-${end} at ${interval} min`);
      }
    }
  }
});

test('waking hours that cross midnight wrap correctly (night shift)', () => {
  assert.deepEqual(labels(120, '10:00', '20:00'), ['20:00', '22:00', '0:00', '2:00', '4:00', '6:00', '8:00']);
});

test('too many reminders are spread evenly within the limit, keeping the evening', () => {
  const slots = reminderSlots(30, '22:00', '07:00');
  assert.ok(slots.length <= MAX_DAILY_REMINDERS);
  assert.ok(slots.at(-1)!.hour >= 21);
});

test('parses the ways people write times', () => {
  for (const [input, want] of [
    ['22:00', '22:00'], ['7:30', '07:30'], ['10:00 PM', '22:00'], ['10 pm', '22:00'], ['10pm', '22:00'],
    ['7:00 am', '07:00'], ['12 AM', '00:00'], ['12:30 PM', '12:30'], ['7 a.m.', '07:00'], [' 00:00 ', '00:00'],
  ]) assert.equal(parseClock(input), want, input);
});

test('rejects things that are not times', () => {
  for (const input of ['', 'soon', '24:00', '13 PM', '0 AM', '7:60', '7', '2200', '10:5']) {
    assert.equal(parseClock(input), null, input);
  }
});

test('formats times and intervals for people', () => {
  assert.equal(formatClock('22:00:00'), '10:00 PM');
  assert.equal(formatClock('00:05'), '12:05 AM');
  assert.equal(formatClock('12:00'), '12:00 PM');
  assert.equal(formatInterval(90), '1 h 30 min');
  assert.equal(formatInterval(120), '2 h');
  assert.equal(formatInterval(45), '45 min');
});
