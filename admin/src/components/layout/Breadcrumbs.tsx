import { ChevronRight } from 'lucide-react';
import { Link, useLocation } from 'react-router';
import { findNavItem, findSection } from '../../nav';

export function Breadcrumbs() {
  const { pathname } = useLocation();
  const item = findNavItem(pathname);
  const section = item && findSection(item);
  const isSubPage = item && pathname !== item.path;

  return (
    <nav aria-label="Breadcrumb" className="mb-4">
      <ol className="flex flex-wrap items-center gap-1 text-xs text-ink-500">
        <li><Link to="/" className="hover:text-ink-900">Home</Link></li>
        {section && (
          <>
            <ChevronRight className="size-3.5 text-ink-400" aria-hidden />
            <li>{section.title}</li>
          </>
        )}
        {item && (
          <>
            <ChevronRight className="size-3.5 text-ink-400" aria-hidden />
            <li>
              {isSubPage ? (
                <Link to={item.path} className="hover:text-ink-900">{item.label}</Link>
              ) : (
                <span aria-current="page" className="font-medium text-ink-900">{item.label}</span>
              )}
            </li>
          </>
        )}
        {!item && (
          <>
            <ChevronRight className="size-3.5 text-ink-400" aria-hidden />
            <li><span aria-current="page" className="font-medium text-ink-900">Not found</span></li>
          </>
        )}
      </ol>
    </nav>
  );
}
