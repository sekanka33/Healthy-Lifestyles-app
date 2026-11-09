import { AlertTriangle, Inbox, Loader2, RefreshCw, type LucideIcon } from 'lucide-react';
import type { ButtonHTMLAttributes, ReactNode } from 'react';

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(' ');
}

/* ---------- Button ---------- */

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
const VARIANTS: Record<Variant, string> = {
  primary: 'bg-brand-600 text-white hover:bg-brand-700 disabled:bg-brand-600/50',
  secondary: 'bg-surface text-ink-900 border border-line hover:bg-canvas disabled:text-ink-400',
  ghost: 'text-ink-700 hover:bg-line-soft disabled:text-ink-400',
  danger: 'bg-bad-strong text-white hover:bg-red-800 disabled:bg-bad-strong/50',
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: 'sm' | 'md';
  icon?: LucideIcon;
  loading?: boolean;
}

export function Button({ variant = 'primary', size = 'md', icon: Icon, loading, className, children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled || loading}
      className={cx(
        'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors disabled:cursor-not-allowed',
        size === 'sm' ? 'h-8 px-3 text-sm' : 'h-10 px-4 text-sm',
        VARIANTS[variant],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : Icon ? <Icon className="size-4" aria-hidden /> : null}
      {children}
    </button>
  );
}

/* ---------- Card ---------- */

export function Card({ title, subtitle, actions, children, className, padded = true }: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <section className={cx('rounded-[var(--radius-card)] border border-line bg-surface shadow-card', className)}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-4 border-b border-line-soft px-5 py-4">
          <div>
            {title && <h2 className="text-sm font-semibold text-ink-900">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-ink-500">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={padded ? 'p-5' : undefined}>{children}</div>
    </section>
  );
}

/* ---------- Badge ---------- */

type Tone = 'neutral' | 'brand' | 'warn' | 'bad' | 'info';
const TONES: Record<Tone, string> = {
  neutral: 'bg-line-soft text-ink-700',
  brand: 'bg-brand-50 text-brand-800',
  warn: 'bg-warn-bg text-warn',
  bad: 'bg-bad-bg text-bad-strong',
  info: 'bg-info-bg text-info',
};

export function Badge({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return <span className={cx('inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium', TONES[tone])}>{children}</span>;
}

/* ---------- KPI card ---------- */

export function KpiCard({ label, value, hint, icon: Icon, loading }: {
  label: string;
  /** null = no data; shown as an em dash, never as 0. */
  value: ReactNode | null;
  hint?: ReactNode;
  icon?: LucideIcon;
  loading?: boolean;
}) {
  return (
    <div className="rounded-[var(--radius-card)] border border-line bg-surface p-4 shadow-card">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-ink-500">{label}</p>
        {Icon && (
          <span className="grid size-7 place-items-center rounded-md bg-brand-50 text-brand-700">
            <Icon className="size-4" aria-hidden />
          </span>
        )}
      </div>
      {loading ? (
        <Skeleton className="mt-3 h-7 w-24" />
      ) : (
        <p className="mt-2 text-2xl font-semibold tracking-tight tabular-nums text-ink-900">{value ?? '—'}</p>
      )}
      {hint && !loading && <p className="mt-1 text-xs text-ink-500">{hint}</p>}
    </div>
  );
}

/* ---------- States ---------- */

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cx('animate-pulse rounded-md bg-line-soft', className)} />;
}

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div role="status" className="flex items-center justify-center gap-2 py-16 text-sm text-ink-500">
      <Loader2 className="size-4 animate-spin" aria-hidden /> {label}
    </div>
  );
}

export function EmptyState({ icon: Icon = Inbox, title, description, action }: {
  icon?: LucideIcon;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
      <span className="grid size-11 place-items-center rounded-full bg-line-soft text-ink-500">
        <Icon className="size-5" aria-hidden />
      </span>
      <h3 className="mt-4 text-sm font-semibold text-ink-900">{title}</h3>
      {description && <p className="mt-1 max-w-md text-sm text-ink-500">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ErrorState({ title = 'Something went wrong', message, onRetry }: {
  title?: string;
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div role="alert" className="flex flex-col items-center justify-center px-6 py-16 text-center">
      <span className="grid size-11 place-items-center rounded-full bg-bad-bg text-bad-strong">
        <AlertTriangle className="size-5" aria-hidden />
      </span>
      <h3 className="mt-4 text-sm font-semibold text-ink-900">{title}</h3>
      {message && <p className="mt-1 max-w-md text-sm text-ink-500">{message}</p>}
      {onRetry && (
        <Button variant="secondary" size="sm" icon={RefreshCw} className="mt-5" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

/* ---------- Page header ---------- */

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-ink-900">{title}</h1>
        {description && <p className="mt-1 text-sm text-ink-500">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
