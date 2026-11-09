import { ChevronRight } from 'lucide-react';
import { Fragment } from 'react';
import { Link, useLocation } from 'react-router';
import { findNavItem, findSection } from '../../nav';

/** Pages outside the sidebar. */
const EXTRA: Record<string, string[]> = {
  '/account/security': ['Account', 'Security'],
  '/ui': ['Design system'],
};

interface Crumb { label: string; to?: string }

function crumbsFor(pathname: string): Crumb[] {
  if (EXTRA[pathname]) return EXTRA[pathname].map((label) => ({ label }));
  const item = findNavItem(pathname);
  if (!item) return [{ label: 'Not found' }];
  const section = findSection(item);
  const isSubPage = pathname !== item.path;
  return [
    ...(section ? [{ label: section.title }] : []),
    { label: item.label, to: isSubPage ? item.path : undefined },
  ];
}

export function Breadcrumbs() {
  const { pathname } = useLocation();
  const crumbs = crumbsFor(pathname);
  return (
    <nav aria-label="Breadcrumb" className="mb-4">
      <ol className="flex flex-wrap items-center gap-1 text-xs text-ink-500">
        <li><Link to="/" className="hover:text-ink-900">Home</Link></li>
        {crumbs.map((c, i) => (
          <Fragment key={c.label}>
            <ChevronRight className="size-3.5 text-ink-400" aria-hidden />
            <li>
              {c.to ? (
                <Link to={c.to} className="hover:text-ink-900">{c.label}</Link>
              ) : i === crumbs.length - 1 ? (
                <span aria-current="page" className="font-medium text-ink-900">{c.label}</span>
              ) : (
                c.label
              )}
            </li>
          </Fragment>
        ))}
      </ol>
    </nav>
  );
}
