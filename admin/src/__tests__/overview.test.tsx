import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { formatMoney, formatPercent, formatRelative } from '../lib/format';
import type { Overview } from '../pages/OverviewPage';
import { apiError, emptyOverview, makeAdmin, renderAt } from '../test/render';

function populated(): Overview {
  const o = emptyOverview();
  o.users = { total: 1204, active_in_range: 380, activity_tracked_since: '2026-11-01', new_in_range: 96, new_this_month: 41, premium: 150, premium_promotional: 3, free: 1054 };
  o.subscriptions = { premium_active: 150, converted_users: 160, conversion_rate: 0.1329, cancellations_in_range: 7, failed_payments_in_range: 2 };
  o.revenue = {
    by_currency: [
      { currency: 'USD', total: '15840.00', in_range: '1650.00', mrr: '1625.21' },
      { currency: 'ZAR', total: '3999.80', in_range: '399.98', mrr: '405.83' },
    ],
    sandbox_transactions_excluded: 4,
  };
  o.series.user_growth = [{ date: '2026-11-08', new_users: 3, total_users: 1201 }, { date: '2026-11-09', new_users: 3, total_users: 1204 }];
  o.series.revenue_monthly = [{ month: '2026-10', amounts: { USD: '1600.00', ZAR: '399.98' } }, { month: '2026-11', amounts: { USD: '1650.00' } }];
  o.feature_usage[0].users = 900;
  o.feature_usage[0].records = 15230;
  o.recent_activity = [
    { type: 'registration', at: '2026-11-09T09:58:00Z', title: 'New registration', detail: 'Ada · a•••@example.com' },
    { type: 'payment_failed', at: '2026-11-09T08:00:00Z', title: 'Payment failed', detail: 'premium_monthly' },
  ];
  return o;
}

const kpi = (label: string) => screen.getByText(label).closest('div')!.parentElement!;

describe('overview page', () => {
  it('shows KPIs from the API response, money per currency', async () => {
    renderAt('/', { admin: makeAdmin(), handlers: { 'GET /overview': () => ({ json: populated() }) } });
    expect(await screen.findByText('1,204')).toBeInTheDocument();
    expect(kpi('Active users')).toHaveTextContent('380');
    expect(kpi('Active users')).toHaveTextContent('tracked since Nov 1');
    expect(kpi('Premium')).toHaveTextContent('incl. 3 promotional');
    expect(kpi('Monthly recurring revenue')).toHaveTextContent('$1,625.21');
    expect(kpi('Monthly recurring revenue')).toHaveTextContent('ZAR');
    expect(kpi('Total revenue')).toHaveTextContent('$15,840.00');
    expect(kpi('Conversion rate')).toHaveTextContent('13.3%');
    expect(kpi('Cancellations')).toHaveTextContent('7');
    expect(screen.getByText('4 sandbox (test) purchases are excluded from all revenue figures.')).toBeInTheDocument();
  });

  it('lists recent activity with masked emails', async () => {
    renderAt('/', { admin: makeAdmin(), handlers: { 'GET /overview': () => ({ json: populated() }) } });
    const card = (await screen.findByText('Recent activity')).closest('section')!;
    expect(within(card).getByText('Ada · a•••@example.com')).toBeInTheDocument();
    expect(within(card).getByText('Payment failed')).toBeInTheDocument();
  });

  it('offers a currency switch when revenue has several currencies', async () => {
    renderAt('/', { admin: makeAdmin(), handlers: { 'GET /overview': () => ({ json: populated() }) } });
    const group = await screen.findByRole('group', { name: 'Currency' });
    expect(within(group).getByRole('button', { name: 'USD' })).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(within(group).getByRole('button', { name: 'ZAR' }));
    expect(within(group).getByRole('button', { name: 'ZAR' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('img', { name: /Monthly revenue in ZAR/ })).toBeInTheDocument();
  });

  it('shows professional empty states for an empty database, never invented numbers', async () => {
    renderAt('/', { admin: makeAdmin() });
    expect(await screen.findByText('No users yet', { selector: 'h3', exact: true }, {})).toBeInTheDocument();
    expect(screen.getByText('No revenue yet')).toBeInTheDocument();
    expect(kpi('Monthly recurring revenue')).toHaveTextContent('—');
    expect(kpi('Monthly recurring revenue')).toHaveTextContent('No verified payments yet');
    expect(kpi('Conversion rate')).toHaveTextContent('—');
    expect(screen.getByText('No activity yet')).toBeInTheDocument();
  });

  it('hides revenue for roles without payment access', async () => {
    const o = populated();
    o.revenue = null;
    o.series.revenue_monthly = null;
    renderAt('/', { admin: makeAdmin('support'), handlers: { 'GET /overview': () => ({ json: o }) } });
    expect(await screen.findByText('1,204')).toBeInTheDocument();
    expect(screen.queryByText('Monthly recurring revenue')).not.toBeInTheDocument();
    expect(screen.queryByText('Total revenue')).not.toBeInTheDocument();
    expect(screen.queryByText('Monthly revenue')).not.toBeInTheDocument();
  });

  it('refetches when the date range changes', async () => {
    const { api } = renderAt('/', { admin: makeAdmin() });
    await screen.findByText('No activity yet');
    await userEvent.click(screen.getByRole('button', { name: 'Last 90 days' }));
    await waitFor(() => expect(api.calls.filter((c) => c.key === 'GET /overview')).toHaveLength(2));
    const url = String(api.fetchMock.mock.calls.at(-1)![0]);
    const params = new URL(url).searchParams;
    const span = (Date.parse(params.get('to')!) - Date.parse(params.get('from')!)) / 86_400_000;
    expect(span).toBe(89);
  });

  it('shows an error state with retry', async () => {
    let calls = 0;
    renderAt('/', {
      admin: makeAdmin(),
      handlers: { 'GET /overview': () => (++calls === 1 ? apiError(500, 'internal_error', 'Something went wrong') : { json: populated() }) },
    });
    expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong');
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('1,204')).toBeInTheDocument();
  });
});

describe('formatting', () => {
  it('money keeps its own currency', () => {
    expect(formatMoney('11', 'USD')).toBe('$11.00');
    expect(formatMoney('199.99', 'ZAR')).toMatch(/ZAR\s?199\.99/);
  });
  it('percent and relative time', () => {
    expect(formatPercent(0.6)).toBe('60%');
    expect(formatPercent(null)).toBeNull();
    const now = new Date('2026-11-09T10:00:00Z');
    expect(formatRelative('2026-11-09T09:58:00Z', now)).toBe('2 min ago');
    expect(formatRelative('2026-11-07T10:00:00Z', now)).toBe('2 d ago');
  });
});
