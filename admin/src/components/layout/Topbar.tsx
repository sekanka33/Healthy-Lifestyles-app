import { Bell, BellOff, ChevronDown, LogOut, Menu, Search, UserRound } from 'lucide-react';
import { useEffect, useRef, useState, type RefObject } from 'react';
import { useNavigate } from 'react-router';
import { searchNav } from '../../nav';
import { cx } from '../ui';

function useDismiss(ref: RefObject<HTMLElement | null>, open: boolean, close: () => void) {
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) close(); };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close(); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey); };
  }, [ref, open, close]);
}

function PageSearch() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const results = searchNav(query);
  useDismiss(box, open, () => setOpen(false));

  const go = (path: string) => { navigate(path); setQuery(''); setOpen(false); };

  return (
    <div ref={box} className="relative w-full max-w-sm">
      <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-400" aria-hidden />
      <input
        type="search"
        role="combobox"
        aria-label="Search pages"
        aria-expanded={open && results.length > 0}
        aria-controls="page-search-results"
        placeholder="Search pages…"
        value={query}
        onChange={(e) => { setQuery(e.target.value); setActive(0); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, results.length - 1)); }
          if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
          if (e.key === 'Enter' && results[active]) go(results[active].path);
        }}
        className="h-9 w-full rounded-lg border border-line bg-canvas pl-9 pr-3 text-sm placeholder:text-ink-400 focus:bg-surface"
      />
      {open && query.trim() && (
        <ul id="page-search-results" role="listbox"
          className="absolute left-0 right-0 top-11 z-50 overflow-hidden rounded-lg border border-line bg-surface py-1 shadow-pop">
          {results.length === 0 && <li className="px-3 py-2 text-sm text-ink-500">No pages match “{query.trim()}”.</li>}
          {results.map((r, i) => (
            <li key={r.path} role="option" aria-selected={i === active}>
              <button type="button" onMouseEnter={() => setActive(i)} onClick={() => go(r.path)}
                className={cx('flex w-full items-start gap-3 px-3 py-2 text-left', i === active && 'bg-line-soft')}>
                <r.icon className="mt-0.5 size-4 text-ink-400" aria-hidden />
                <span>
                  <span className="block text-sm font-medium text-ink-900">{r.label}</span>
                  <span className="block text-xs text-ink-500">{r.description}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function NotificationsMenu() {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useDismiss(box, open, () => setOpen(false));
  return (
    <div ref={box} className="relative">
      <button type="button" aria-label="Notifications" aria-expanded={open} onClick={() => setOpen((o) => !o)}
        className="grid size-9 place-items-center rounded-lg text-ink-500 hover:bg-line-soft hover:text-ink-900">
        <Bell className="size-[18px]" />
      </button>
      {open && (
        <div role="dialog" aria-label="Notifications"
          className="absolute right-0 top-11 z-50 w-80 rounded-lg border border-line bg-surface shadow-pop">
          <p className="border-b border-line-soft px-4 py-3 text-sm font-semibold">Notifications</p>
          <div className="flex flex-col items-center px-6 py-8 text-center">
            <BellOff className="size-5 text-ink-400" aria-hidden />
            <p className="mt-2 text-sm text-ink-500">No notifications. Alerts for failed payments and service outages will appear here.</p>
          </div>
        </div>
      )}
    </div>
  );
}

export interface AccountSummary {
  name: string;
  email: string;
  role: string;
}

function AccountMenu({ account, onSignOut }: { account: AccountSummary | null; onSignOut?: () => void }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useDismiss(box, open, () => setOpen(false));
  const initials = account ? account.name.split(/\s+/).map((p) => p[0]).join('').slice(0, 2).toUpperCase() : null;

  return (
    <div ref={box} className="relative">
      <button type="button" aria-label="Account menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}
        className="flex h-9 items-center gap-2 rounded-lg pl-1 pr-2 hover:bg-line-soft">
        <span className="grid size-7 place-items-center rounded-full bg-brand-100 text-xs font-semibold text-brand-800">
          {initials ?? <UserRound className="size-4" aria-hidden />}
        </span>
        <span className="hidden text-left leading-tight md:block">
          <span className="block text-sm font-medium text-ink-900">{account?.name ?? 'Not signed in'}</span>
          {account && <span className="block text-[11px] text-ink-500">{account.role}</span>}
        </span>
        <ChevronDown className="hidden size-4 text-ink-400 md:block" aria-hidden />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-11 z-50 w-60 rounded-lg border border-line bg-surface py-1 shadow-pop">
          {account && (
            <div className="border-b border-line-soft px-4 py-3">
              <p className="truncate text-sm font-medium">{account.name}</p>
              <p className="truncate text-xs text-ink-500">{account.email}</p>
            </div>
          )}
          <button type="button" role="menuitem" disabled={!onSignOut} onClick={() => { setOpen(false); onSignOut?.(); }}
            className="flex w-full items-center gap-2 px-4 py-2 text-sm text-ink-700 hover:bg-line-soft disabled:cursor-not-allowed disabled:text-ink-400 disabled:hover:bg-transparent">
            <LogOut className="size-4" aria-hidden /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}

export function Topbar({ onOpenMobileNav, account, onSignOut }: {
  onOpenMobileNav: () => void;
  account: AccountSummary | null;
  onSignOut?: () => void;
}) {
  return (
    <header className="sticky top-0 z-20 flex h-16 shrink-0 items-center gap-3 border-b border-line bg-surface/95 px-4 backdrop-blur sm:px-6">
      <button type="button" onClick={onOpenMobileNav} aria-label="Open navigation"
        className="grid size-9 place-items-center rounded-lg text-ink-500 hover:bg-line-soft lg:hidden">
        <Menu className="size-5" />
      </button>
      <PageSearch />
      <div className="ml-auto flex items-center gap-1">
        <NotificationsMenu />
        <AccountMenu account={account} onSignOut={onSignOut} />
      </div>
    </header>
  );
}
