import type { ReactNode } from 'react';
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { formatCompact } from '../../lib/format';

/* Shared specs (dataviz): 2px lines, ≤24px bars with 4px rounded data-end, 10% area wash,
   hairline solid grid, axis text in muted ink. Colours come from the CSS chart tokens. */
const C1 = 'var(--color-chart-1)';
const GRID = 'var(--color-chart-grid)';
const AXIS = { fontSize: 11, fill: 'var(--color-ink-500)' };

export interface TooltipRow { label: string; value: string; color?: string }

export function ChartTooltip({ title, rows }: { title: string; rows: TooltipRow[] }) {
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-pop">
      <p className="font-medium text-ink-900">{title}</p>
      {rows.map((r) => (
        <p key={r.label} className="mt-1 flex items-center gap-2 text-ink-700">
          {r.color && <span className="size-2 rounded-full" style={{ background: r.color }} aria-hidden />}
          <span>{r.label}</span>
          <span className="ml-auto pl-3 font-medium tabular-nums text-ink-900">{r.value}</span>
        </p>
      ))}
    </div>
  );
}

type TipFn<T> = (point: T) => { title: string; rows: TooltipRow[] };

function tooltip<T>(fn: TipFn<T>) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return ({ active, payload }: any) => {
    if (!active || !payload?.length) return null;
    const { title, rows } = fn(payload[0].payload as T);
    return <ChartTooltip title={title} rows={rows} />;
  };
}

function Frame({ height = 240, label, children }: { height?: number; label: string; children: ReactNode }) {
  return (
    <div role="img" aria-label={label} style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">{children as never}</ResponsiveContainer>
    </div>
  );
}

export function TrendArea<T extends object>({ data, x, y, label, xFormat, tip, height }: {
  data: T[]; x: keyof T & string; y: keyof T & string; label: string;
  xFormat: (v: string) => string; tip: TipFn<T>; height?: number;
}) {
  return (
    <Frame label={label} height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey={x as never} tickFormatter={xFormat} tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} minTickGap={24} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} allowDecimals={false} tickFormatter={formatCompact} />
        <Tooltip content={tooltip(tip)} cursor={{ stroke: 'var(--color-ink-400)', strokeWidth: 1 }} />
        <Area type="monotone" dataKey={y as never} stroke={C1} strokeWidth={2} fill={C1} fillOpacity={0.1}
          activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--color-surface)' }} isAnimationActive={false} />
      </AreaChart>
    </Frame>
  );
}

export function TrendLine<T extends object>({ data, x, y, label, xFormat, yFormat, tip, domain }: {
  data: T[]; x: keyof T & string; y: keyof T & string; label: string;
  xFormat: (v: string) => string; yFormat: (v: number) => string; tip: TipFn<T>; domain?: [number, number | 'auto'];
}) {
  return (
    <Frame label={label}>
      <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey={x as never} tickFormatter={xFormat} tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} minTickGap={16} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} tickFormatter={yFormat} domain={domain ?? [0, 'auto']} />
        <Tooltip content={tooltip(tip)} cursor={{ stroke: 'var(--color-ink-400)', strokeWidth: 1 }} />
        <Line type="monotone" dataKey={y as never} stroke={C1} strokeWidth={2} dot={false} connectNulls
          activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--color-surface)' }} isAnimationActive={false} />
      </LineChart>
    </Frame>
  );
}

export function Columns<T extends object>({ data, x, y, label, xFormat, yFormat, tip }: {
  data: T[]; x: keyof T & string; y: keyof T & string; label: string;
  xFormat: (v: string) => string; yFormat: (v: number) => string; tip: TipFn<T>;
}) {
  return (
    <Frame label={label}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey={x as never} tickFormatter={xFormat} tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} width={52} tickFormatter={yFormat} />
        <Tooltip content={tooltip(tip)} cursor={{ fill: 'var(--color-line-soft)' }} />
        <Bar dataKey={y as never} fill={C1} maxBarSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </Frame>
  );
}

/** Horizontal bars in plain HTML: value at the tip, label on the left, 24px max thickness. */
export function HBars({ rows, label }: { rows: { key: string; label: string; value: number; display: string; note?: string }[]; label: string }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul aria-label={label} className="space-y-4">
      {rows.map((r) => (
        <li key={r.key}>
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span className="text-ink-700">{r.label}</span>
            <span className="font-medium tabular-nums text-ink-900">{r.display}</span>
          </div>
          <div className="mt-1.5 h-2.5 rounded-r bg-line-soft">
            <div className="h-full rounded-r" style={{ width: `${(r.value / max) * 100}%`, background: C1, minWidth: r.value ? 4 : 0 }} />
          </div>
          {r.note && <p className="mt-1 text-xs text-ink-500">{r.note}</p>}
        </li>
      ))}
    </ul>
  );
}

/** Part-to-whole for two to three parts: one segmented bar with a 2px surface gap, legend with values. */
export function SplitBar({ parts, label }: { parts: { label: string; value: number; color: string; display: string }[]; label: string }) {
  const total = parts.reduce((s, p) => s + p.value, 0);
  return (
    <div>
      <div role="img" aria-label={label} className="flex h-6 gap-0.5 overflow-hidden rounded">
        {parts.filter((p) => p.value > 0).map((p) => (
          <div key={p.label} style={{ width: `${(p.value / total) * 100}%`, background: p.color }} title={`${p.label}: ${p.display}`} />
        ))}
      </div>
      <ul className="mt-4 space-y-2">
        {parts.map((p) => (
          <li key={p.label} className="flex items-center gap-2 text-sm">
            <span className="size-2.5 rounded-sm" style={{ background: p.color }} aria-hidden />
            <span className="text-ink-700">{p.label}</span>
            <span className="ml-auto font-medium tabular-nums text-ink-900">{p.display}</span>
            <span className="w-12 text-right text-xs tabular-nums text-ink-500">{total ? `${Math.round((p.value / total) * 100)}%` : '—'}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
