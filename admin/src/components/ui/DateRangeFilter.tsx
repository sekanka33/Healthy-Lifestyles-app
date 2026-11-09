import { CalendarRange } from 'lucide-react';
import { useState } from 'react';
import { Button, cx } from './index';

export type PresetKey = 'today' | '7d' | '30d' | '90d' | 'custom';

export interface DateRange {
  preset: PresetKey;
  /** Inclusive local dates, YYYY-MM-DD. */
  from: string;
  to: string;
}

export const PRESETS: { key: Exclude<PresetKey, 'custom'>; label: string; days: number }[] = [
  { key: 'today', label: 'Today', days: 1 },
  { key: '7d', label: 'Last 7 days', days: 7 },
  { key: '30d', label: 'Last 30 days', days: 30 },
  { key: '90d', label: 'Last 90 days', days: 90 },
];

/** Max span the backend accepts for one query; keeps aggregate queries bounded. */
export const MAX_RANGE_DAYS = 366;

export function isoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export function presetRange(key: Exclude<PresetKey, 'custom'>, today: Date = new Date()): DateRange {
  const days = PRESETS.find((p) => p.key === key)!.days;
  const from = new Date(today);
  from.setDate(from.getDate() - (days - 1));
  return { preset: key, from: isoDate(from), to: isoDate(today) };
}

/** Returns an error message, or null when the custom range is valid. */
export function validateRange(from: string, to: string, today: Date = new Date()): string | null {
  const re = /^\d{4}-\d{2}-\d{2}$/;
  if (!re.test(from) || !re.test(to)) return 'Choose both a start and an end date.';
  const f = new Date(from + 'T00:00:00');
  const t = new Date(to + 'T00:00:00');
  if (Number.isNaN(f.getTime()) || Number.isNaN(t.getTime())) return 'Enter valid dates.';
  if (f > t) return 'The start date must be on or before the end date.';
  if (to > isoDate(today)) return 'The end date cannot be in the future.';
  const span = Math.round((t.getTime() - f.getTime()) / 86_400_000) + 1;
  if (span > MAX_RANGE_DAYS) return `Choose a range of at most ${MAX_RANGE_DAYS} days.`;
  return null;
}

export function DateRangeFilter({ value, onChange }: { value: DateRange; onChange: (r: DateRange) => void }) {
  const [customOpen, setCustomOpen] = useState(value.preset === 'custom');
  const [from, setFrom] = useState(value.from);
  const [to, setTo] = useState(value.to);
  const [error, setError] = useState<string | null>(null);

  const applyCustom = () => {
    const problem = validateRange(from, to);
    setError(problem);
    if (!problem) onChange({ preset: 'custom', from, to });
  };

  return (
    <div className="flex flex-col items-start gap-2 sm:items-end">
      <div role="group" aria-label="Date range" className="inline-flex flex-wrap rounded-lg border border-line bg-surface p-0.5">
        {PRESETS.map((p) => (
          <button
            key={p.key}
            type="button"
            aria-pressed={value.preset === p.key}
            onClick={() => {
              setCustomOpen(false);
              setError(null);
              onChange(presetRange(p.key));
            }}
            className={cx(
              'h-8 rounded-md px-3 text-xs font-medium transition-colors',
              value.preset === p.key ? 'bg-brand-50 text-brand-800' : 'text-ink-500 hover:text-ink-900',
            )}
          >
            {p.label}
          </button>
        ))}
        <button
          type="button"
          aria-pressed={value.preset === 'custom'}
          aria-expanded={customOpen}
          onClick={() => setCustomOpen((o) => !o)}
          className={cx(
            'inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-xs font-medium transition-colors',
            value.preset === 'custom' ? 'bg-brand-50 text-brand-800' : 'text-ink-500 hover:text-ink-900',
          )}
        >
          <CalendarRange className="size-3.5" aria-hidden /> Custom
        </button>
      </div>

      {customOpen && (
        <div className="flex flex-wrap items-end gap-2 rounded-lg border border-line bg-surface p-3 shadow-card">
          <label className="text-xs text-ink-500">
            From
            <input type="date" value={from} max={isoDate(new Date())} onChange={(e) => setFrom(e.target.value)}
              className="mt-1 block h-8 rounded-md border border-line px-2 text-sm text-ink-900" />
          </label>
          <label className="text-xs text-ink-500">
            To
            <input type="date" value={to} max={isoDate(new Date())} onChange={(e) => setTo(e.target.value)}
              className="mt-1 block h-8 rounded-md border border-line px-2 text-sm text-ink-900" />
          </label>
          <Button size="sm" onClick={applyCustom}>Apply</Button>
          {error && <p role="alert" className="w-full text-xs text-bad-strong">{error}</p>}
        </div>
      )}
    </div>
  );
}
