import { Route, Routes } from 'react-router';
import { AppShell } from './components/layout/AppShell';
import { NAV_ITEMS } from './nav';
import { NotFoundPage } from './pages/NotFoundPage';
import { SectionPage } from './pages/SectionPage';
import { StyleGuidePage } from './pages/StyleGuidePage';

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        {NAV_ITEMS.map((item) =>
          item.path === '/' ? (
            <Route key={item.path} index element={<SectionPage item={item} />} />
          ) : (
            <Route key={item.path} path={item.path.slice(1)} element={<SectionPage item={item} />} />
          ),
        )}
        <Route path="ui" element={<StyleGuidePage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
