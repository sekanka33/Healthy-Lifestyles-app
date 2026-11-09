import { ChevronsLeft, ChevronsRight, X } from 'lucide-react';
import { NavLink } from 'react-router';
import { NAV } from '../../nav';
import { cx } from '../ui';
import { Logo } from './Logo';

export function Sidebar({ collapsed, onToggleCollapsed, mobileOpen, onCloseMobile }: {
  collapsed: boolean;
  onToggleCollapsed: () => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}) {
  return (
    <>
      {/* Mobile backdrop */}
      <div
        aria-hidden
        onClick={onCloseMobile}
        className={cx('fixed inset-0 z-30 bg-ink-900/30 lg:hidden', mobileOpen ? 'block' : 'hidden')}
      />
      <aside
        aria-label="Main navigation"
        className={cx(
          'fixed inset-y-0 left-0 z-40 flex flex-col border-r border-line bg-surface transition-[width,transform] duration-200',
          'lg:static lg:translate-x-0',
          mobileOpen ? 'translate-x-0' : '-translate-x-full',
          collapsed ? 'w-64 lg:w-[72px]' : 'w-64',
        )}
      >
        <div className={cx('flex h-16 shrink-0 items-center border-b border-line-soft', collapsed ? 'px-5 lg:justify-center lg:px-0' : 'px-5')}>
          <Logo compact={collapsed} />
          <button type="button" onClick={onCloseMobile} aria-label="Close navigation"
            className="ml-auto rounded-md p-1.5 text-ink-500 hover:bg-line-soft lg:hidden">
            <X className="size-5" />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-4">
          {NAV.map((section) => (
            <div key={section.title} className="mb-5 last:mb-0">
              <p className={cx('mb-1.5 px-2 text-[11px] font-semibold uppercase tracking-wider text-ink-400', collapsed && 'lg:sr-only')}>
                {section.title}
              </p>
              <ul className="space-y-0.5">
                {section.items.map((item) => (
                  <li key={item.path}>
                    <NavLink
                      to={item.path}
                      end={item.path === '/'}
                      onClick={onCloseMobile}
                      title={collapsed ? item.label : undefined}
                      className={({ isActive }) =>
                        cx(
                          'group flex h-9 items-center gap-3 rounded-lg px-2 text-sm font-medium transition-colors',
                          collapsed && 'lg:justify-center lg:px-0',
                          isActive ? 'bg-brand-50 text-brand-800' : 'text-ink-700 hover:bg-line-soft hover:text-ink-900',
                        )
                      }
                    >
                      {({ isActive }) => (
                        <>
                          <item.icon className={cx('size-[18px] shrink-0', isActive ? 'text-brand-600' : 'text-ink-400 group-hover:text-ink-700')} aria-hidden />
                          <span className={cx('truncate', collapsed && 'lg:sr-only')}>{item.label}</span>
                        </>
                      )}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>

        <div className="hidden border-t border-line-soft p-3 lg:block">
          <button
            type="button"
            onClick={onToggleCollapsed}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            className={cx('flex h-9 w-full items-center gap-3 rounded-lg px-2 text-sm text-ink-500 hover:bg-line-soft hover:text-ink-900', collapsed && 'justify-center px-0')}
          >
            {collapsed ? <ChevronsRight className="size-[18px]" aria-hidden /> : <ChevronsLeft className="size-[18px]" aria-hidden />}
            {!collapsed && <span>Collapse</span>}
          </button>
        </div>
      </aside>
    </>
  );
}
