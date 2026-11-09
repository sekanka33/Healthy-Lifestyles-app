import { Lock } from 'lucide-react';
import type { ReactNode } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router';
import { useAuth } from '../lib/auth';
import { Card, EmptyState, LoadingState } from './ui';

export const SECURITY_PATH = '/account/security';

/** Signed-in admins only. While MFA setup is pending, only the security page is reachable. */
export function RequireAuth() {
  const { status, admin } = useAuth();
  const location = useLocation();
  if (status === 'loading') return <div className="flex h-full items-center justify-center"><LoadingState label="Checking your session…" /></div>;
  if (status === 'signed_out') return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (admin?.mfa_setup_needed && location.pathname !== SECURITY_PATH) return <Navigate to={SECURITY_PATH} replace />;
  return <Outlet />;
}

/** Hides a page the role can't use. The API enforces the same rule; this only avoids a dead screen. */
export function RequirePermission({ permission, children }: { permission: string; children: ReactNode }) {
  const { can } = useAuth();
  if (can(permission)) return <>{children}</>;
  return (
    <Card>
      <EmptyState icon={Lock} title="You don't have access to this page"
        description="Your role doesn't include this section. Ask the account owner if you need access." />
    </Card>
  );
}
