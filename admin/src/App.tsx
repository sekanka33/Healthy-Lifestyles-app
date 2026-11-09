import { Route, Routes } from 'react-router';
import { RequireAuth, RequirePermission } from './components/guards';
import { AppShell } from './components/layout/AppShell';
import { useAuth } from './lib/auth';
import { NAV_ITEMS } from './nav';
import { LoginPage } from './pages/LoginPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { SectionPage } from './pages/SectionPage';
import { SecurityPage } from './pages/SecurityPage';
import { StyleGuidePage } from './pages/StyleGuidePage';

function Shell() {
  const { admin, logout } = useAuth();
  return (
    <AppShell
      account={admin ? { name: admin.full_name, email: admin.email, role: admin.role_label } : null}
      onSignOut={() => void logout()}
    />
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<Shell />}>
          {NAV_ITEMS.map((item) => {
            const page = <RequirePermission permission={item.permission}><SectionPage item={item} /></RequirePermission>;
            return item.path === '/'
              ? <Route key={item.path} index element={page} />
              : <Route key={item.path} path={item.path.slice(1)} element={page} />;
          })}
          <Route path="account/security" element={<SecurityPage />} />
          <Route path="ui" element={<StyleGuidePage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
