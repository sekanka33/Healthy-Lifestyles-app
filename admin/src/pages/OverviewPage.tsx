import {
  Activity, AlertTriangle, BadgeDollarSign, CreditCard, Crown, Percent, RefreshCw, ShieldCheck, TrendingDown,
  UserPlus, Users, Wallet, XCircle, type LucideIcon,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import { Columns, HBars, SplitBar, TrendArea, TrendLine } from '../components/charts';
import { Button, Card, EmptyState, ErrorState, KpiCard, LoadingState, PageHeader, cx } from '../components/ui';
import { DateRangeFilter, presetRange, type DateRange } from '../components/ui/DateRangeFilter';
import {
  formatDay, formatMoney, formatMonth, formatNumber, formatPercent, formatRelative,
} from '../lib/format';
import { useApiQuery } from '../lib/useApiQuery';

export interface Overview {
  range: { from: string; to: string };
  generated_at: string;
  users: {
    total: number; active_in_range: number; activity_tracked_since: string | null; new_in_range: number;
    new_this_month: number; premium: number; premium_promotional: number; free: number;
  };
  subscriptions: {
    premium_active: number; converted_users: number; conversion_rate: number | null;
    cancellations_in_range: number; failed_payments_in_range: number;
  };
  revenue: null | {
    by_currency: { currency: string; total: string; in_range: string; mrr: string }[];
    sandbox_transactions_excluded: number;
  };
  series: {
    user_growth: { date: string; new_users: number; total_users: number }[];
    active_users: { date: string; active_users: number }[];
    conversion_monthly: { month: string; registered_users: number; converted_users: number; rate: number | null }[];
    revenue_monthly: null | { month: string; amounts: Record<string, string> }[];
  };
  feature_usage: { feature: string; label: string; users: number; records: number; record_label: string; extra?: Record<string, number> }[];
  recent_activity: { type: string; at: string; title: string; detail: string | null }[];
}

const ACTIVITY_ICONS: Record<string, { icon: LucideIcon; tone: string }> = {
  registration: { icon: UserPlus, tone: 'bg-brand-50 text-brand-700' },
  subscription: { icon: Crown, tone: 'bg-brand-50 text-brand-700' },
  payment: { icon: CreditCard, tone: 'bg-brand-50 text-brand-700' },
  payment_pending: { icon: CreditCard, tone: 'bg-line-soft text-ink-500' },
  payment_failed: { icon: AlertTriangle, tone: 'bg-bad-bg text-bad-strong' },
  refund: { icon: RefreshCw, tone: 'bg-warn-bg text-warn' },
  cancellation: { icon: XCircle, tone: 'bg-warn-bg text-warn' },
  admin_action: { icon: ShieldCheck, tone: 'bg-info-bg text-info' },
};

function moneyList(rows: { currency: string; value: string }[]): { value: string | null; hint?: string } {
  if (rows.length === 0) return { value: null, hint: 'No verified payments yet' };
  const [first, ...rest] = rows;
  return { value: formatMoney(first.value, first.currency), hint: rest.length ? rest.map((r) => formatMoney(r.value, r.currency)).join(' · ') : undefined };
}

function Kpis({ o }: { o: Overview }) {
  const { users: u, subscriptions: s, revenue } = o;
  const mrr = revenue && moneyList(revenue.by_currency.map((c) => ({ currency: c.currency, value: c.mrr })));
  const total = revenue && moneyList(revenue.by_currency.map((c) => ({ currency: c.currency, value: c.total })));
  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
      <KpiCard label="Registered users" value={formatNumber(u.total)} icon={Users} hint={`${formatNumber(u.new_in_range)} joined in range`} />
      <KpiCard label="Active users" value={formatNumber(u.active_in_range)} icon={Activity}
        hint={u.activity_tracked_since ? `In range · tracked since ${formatDay(u.activity_tracked_since)}` : 'Tracking starts with the next app use'} />
      <KpiCard label="New this month" value={formatNumber(u.new_this_month)} icon={UserPlus} />
      <KpiCard label="Free plan" value={formatNumber(u.free)} icon={Users} />
      <KpiCard label="Premium" value={formatNumber(u.premium)} icon={Crown}
        hint={u.premium_promotional ? `incl. ${formatNumber(u.premium_promotional)} promotional` : undefined} />
      {mrr && <KpiCard label="Monthly recurring revenue" value={mrr.value} hint={mrr.hint} icon={Wallet} />}
      {total && <KpiCard label="Total revenue" value={total.value} hint={total.hint} icon={BadgeDollarSign} />}
      <KpiCard label="Cancellations" value={formatNumber(s.cancellations_in_range)} icon={TrendingDown}
        hint={`In range · ${formatNumber(s.failed_payments_in_range)} failed payments`} />
      <KpiCard label="Conversion rate" value={formatPercent(s.conversion_rate)} icon={Percent}
        hint={`${formatNumber(s.converted_users)} users have paid`} />
    </div>
  );
}

function RevenueChart({ months }: { months: NonNullable<Overview['series']['revenue_monthly']> }) {
  const currencies = useMemo(() => [...new Set(months.flatMap((m) => Object.keys(m.amounts)))].sort(), [months]);
  const [picked, setPicked] = useState<string | null>(null);
  const currency = picked && currencies.includes(picked) ? picked : currencies[0];
  if (!currency) return <EmptyState icon={BadgeDollarSign} title="No revenue yet" description="Verified store payments from the last 12 months will appear here." />;
  const data = months.map((m) => ({ month: m.month, amount: Number(m.amounts[currency] ?? 0) }));
  return (
    <>
      {currencies.length > 1 && (
        <div role="group" aria-label="Currency" className="mb-3 inline-flex rounded-lg border border-line p-0.5">
          {currencies.map((c) => (
            <button key={c} type="button" aria-pressed={c === currency} onClick={() => setPicked(c)}
              className={cx('h-7 rounded-md px-2.5 text-xs font-medium', c === currency ? 'bg-brand-50 text-brand-800' : 'text-ink-500 hover:text-ink-900')}>
              {c}
            </button>
          ))}
        </div>
      )}
      <Columns data={data} x="month" y="amount" label={`Monthly revenue in ${currency}, last 12 months`}
        xFormat={formatMonth} yFormat={(v) => formatMoney(v, currency).replace(/\.00$/, '')}
        tip={(p) => ({ title: formatMonth(p.month), rows: [{ label: 'Revenue', value: formatMoney(p.amount, currency) }] })} />
    </>
  );
}

function RecentActivity({ items }: { items: Overview['recent_activity'] }) {
  if (items.length === 0) return <EmptyState title="No activity yet" description="Registrations, subscriptions, payments and admin actions will be listed here." />;
  return (
    <ul className="divide-y divide-line-soft">
      {items.map((i, idx) => {
        const meta = ACTIVITY_ICONS[i.type] ?? ACTIVITY_ICONS.admin_action;
        return (
          <li key={`${i.type}-${i.at}-${idx}`} className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
            <span className={cx('grid size-8 shrink-0 place-items-center rounded-full', meta.tone)}><meta.icon className="size-4" aria-hidden /></span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-ink-900">{i.title}</p>
              {i.detail && <p className="truncate text-xs text-ink-500">{i.detail}</p>}
            </div>
            <time dateTime={i.at} className="shrink-0 text-xs text-ink-500">{formatRelative(i.at)}</time>
          </li>
        );
      })}
    </ul>
  );
}

export function OverviewPage() {
  const [range, setRange] = useState<DateRange>(() => presetRange('30d'));
  const { data: o, error, loading, reload } = useApiQuery<Overview>(`/overview?from=${range.from}&to=${range.to}`);

  const header = (
    <PageHeader title="Overview" description="Live business metrics from the LifePulse database."
      actions={<DateRangeFilter value={range} onChange={setRange} />} />
  );
  if (error && !o) return <>{header}<Card><ErrorState message={error.message} onRetry={reload} /></Card></>;
  if (!o) return <>{header}<Card><LoadingState label="Loading metrics…" /></Card></>;

  const growthHasData = o.series.user_growth.some((p) => p.total_users > 0);
  const conversionHasData = o.series.conversion_monthly.some((p) => p.registered_users > 0);
  const premiumShare = o.users.total ? o.users.premium / o.users.total : null;

  return (
    <>
      {header}
      <div className={cx('space-y-6 transition-opacity', loading && 'opacity-60')} aria-busy={loading}>
        {error && (
          <p role="alert" className="flex items-center justify-between rounded-lg bg-bad-bg px-3 py-2 text-sm text-bad-strong">
            Couldn't refresh: {error.message}
            <Button size="sm" variant="secondary" onClick={reload}>Retry</Button>
          </p>
        )}
        <Kpis o={o} />

        <div className="grid gap-6 lg:grid-cols-3">
          <Card className="lg:col-span-2" title="User growth" subtitle={`Registered users, ${formatDay(o.range.from)} – ${formatDay(o.range.to)}`}>
            {growthHasData ? (
              <TrendArea data={o.series.user_growth} x="date" y="total_users" label="Registered users over time" xFormat={formatDay}
                tip={(p) => ({ title: formatDay(p.date), rows: [
                  { label: 'Registered users', value: formatNumber(p.total_users)! },
                  { label: 'Joined that day', value: formatNumber(p.new_users)! },
                ] })} />
            ) : <EmptyState icon={Users} title="No users yet" description="Registrations will be charted here." />}
          </Card>

          <Card title="Free vs Premium" subtitle="Current plan of every registered user">
            {o.users.total ? (
              <SplitBar label={`Free ${o.users.free}, Premium ${o.users.premium}`} parts={[
                { label: 'Premium', value: o.users.premium, color: 'var(--color-chart-1)', display: formatNumber(o.users.premium)! },
                { label: 'Free', value: o.users.free, color: 'var(--color-chart-2)', display: formatNumber(o.users.free)! },
              ]} />
            ) : <EmptyState icon={Crown} title="No users yet" />}
            {premiumShare != null && o.users.premium_promotional > 0 && (
              <p className="mt-4 text-xs text-ink-500">Premium includes {formatNumber(o.users.premium_promotional)} promotional (unpaid) grants.</p>
            )}
          </Card>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          {o.series.revenue_monthly && (
            <Card title="Monthly revenue" subtitle="Verified production payments, refunds and sandbox excluded">
              <RevenueChart months={o.series.revenue_monthly} />
            </Card>
          )}
          <Card title="Subscription conversion" subtitle="Share of registered users who have ever paid, by month">
            {conversionHasData ? (
              <TrendLine data={o.series.conversion_monthly} x="month" y="rate" label="Conversion rate by month"
                xFormat={formatMonth} yFormat={(v) => formatPercent(v, 0)!} domain={[0, 'auto']}
                tip={(p) => ({ title: formatMonth(p.month), rows: [
                  { label: 'Conversion', value: formatPercent(p.rate) ?? '—' },
                  { label: 'Paid users', value: `${formatNumber(p.converted_users)} of ${formatNumber(p.registered_users)}` },
                ] })} />
            ) : <EmptyState icon={Percent} title="Not enough data" description="Conversion appears once users register." />}
          </Card>
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          <Card title="Feature usage" subtitle="Distinct users in the selected range (aggregated, no health details)">
            <HBars label="Users per feature" rows={o.feature_usage.map((f) => ({
              key: f.feature, label: f.label, value: f.users, display: `${formatNumber(f.users)} users`,
              note: `${formatNumber(f.records)} ${f.record_label}`,
            }))} />
          </Card>
          <Card className="lg:col-span-2" title="Recent activity" subtitle="Latest events across the business">
            <RecentActivity items={o.recent_activity} />
          </Card>
        </div>

        {o.revenue && o.revenue.sandbox_transactions_excluded > 0 && (
          <p className="text-xs text-ink-500">{formatNumber(o.revenue.sandbox_transactions_excluded)} sandbox (test) purchases are excluded from all revenue figures.</p>
        )}
      </div>
    </>
  );
}
