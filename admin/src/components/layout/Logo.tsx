import { cx } from '../ui';

/** LifePulse mark: a heartbeat line inside a rounded emerald tile. */
export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-brand-600 text-white">
        <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M3 12h4l2-5 4 10 2-5h6" />
        </svg>
      </span>
      <span className={cx('leading-tight', compact && 'lg:sr-only')}>
        <span className="block text-sm font-semibold text-ink-900">LifePulse</span>
        <span className="block text-[11px] font-medium text-ink-500">Admin</span>
      </span>
    </div>
  );
}
