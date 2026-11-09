const nf = new Intl.NumberFormat('en-US');

export const formatNumber = (n: number | null | undefined): string | null => (n == null ? null : nf.format(n));

export function formatPercent(rate: number | null | undefined, digits = 1): string | null {
  if (rate == null) return null;
  return `${(rate * 100).toFixed(digits).replace(/\.0+$/, '')}%`;
}

/** Amounts arrive as decimal strings and are never converted between currencies. */
export function formatMoney(amount: string | number, currency: string): string {
  const value = typeof amount === 'string' ? Number(amount) : amount;
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency, maximumFractionDigits: 2 }).format(value);
  } catch {
    return `${currency} ${value.toFixed(2)}`;
  }
}

export function formatCompact(n: number): string {
  return Math.abs(n) >= 10_000 ? new Intl.NumberFormat('en-US', { notation: 'compact' }).format(n) : nf.format(n);
}

export function formatDay(iso: string): string {
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export function formatMonth(ym: string): string {
  return new Date(ym + '-01T00:00:00').toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
}

export function formatRelative(iso: string, now: Date = new Date()): string {
  const diff = (now.getTime() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86_400) return `${Math.floor(diff / 3600)} h ago`;
  if (diff < 7 * 86_400) return `${Math.floor(diff / 86_400)} d ago`;
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}
