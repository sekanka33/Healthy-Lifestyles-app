import {
  Activity,
  BarChart3,
  CreditCard,
  Droplets,
  FileText,
  Gauge,
  KeyRound,
  LayoutDashboard,
  LifeBuoy,
  Mail,
  Pill,
  ScrollText,
  Settings,
  ShieldCheck,
  Tags,
  Users,
  type LucideIcon,
} from 'lucide-react';

/**
 * Single source of truth for the sidebar, breadcrumbs, page titles and quick search.
 * `permission` is the backend permission needed to see the page. The backend enforces it on
 * every endpoint (Phase 3+); hiding a link here is only a convenience.
 */
export interface NavItem {
  path: string;
  label: string;
  description: string;
  icon: LucideIcon;
  permission: string;
  /** Phase in which the page gets real data; used for the "not built yet" state. */
  phase: number;
}

export interface NavSection {
  title: string;
  items: NavItem[];
}

export const NAV: NavSection[] = [
  {
    title: 'Business management',
    items: [
      { path: '/', label: 'Overview', description: 'Key business metrics and recent activity', icon: LayoutDashboard, permission: 'dashboard.read', phase: 4 },
      { path: '/users', label: 'User Management', description: 'Search, inspect, suspend and reactivate accounts', icon: Users, permission: 'users.read', phase: 5 },
      { path: '/subscriptions', label: 'Subscription Management', description: 'Free and Premium subscriptions, renewals and churn', icon: Tags, permission: 'subscriptions.read', phase: 6 },
      { path: '/payments', label: 'Payments & Revenue', description: 'Verified store transactions, revenue and refunds', icon: CreditCard, permission: 'payments.read', phase: 6 },
      { path: '/plans', label: 'Plans & Pricing', description: 'Plan catalogue and advertised prices', icon: KeyRound, permission: 'plans.read', phase: 6 },
    ],
  },
  {
    title: 'Application management',
    items: [
      { path: '/water', label: 'Water Tracking', description: 'Aggregated hydration feature usage', icon: Droplets, permission: 'features.read', phase: 8 },
      { path: '/medication', label: 'Medication Management', description: 'Aggregated medication feature adoption', icon: Pill, permission: 'features.read', phase: 8 },
      { path: '/fitness', label: 'Fitness Management', description: 'Aggregated workouts and integration status', icon: Activity, permission: 'features.read', phase: 8 },
      { path: '/emails', label: 'Notifications & Emails', description: 'Email delivery history and templates', icon: Mail, permission: 'emails.read', phase: 9 },
    ],
  },
  {
    title: 'Reporting',
    items: [
      { path: '/analytics', label: 'Analytics', description: 'Active users, retention, conversion and churn', icon: BarChart3, permission: 'analytics.read', phase: 7 },
      { path: '/reports', label: 'Reports', description: 'CSV and PDF exports', icon: FileText, permission: 'reports.read', phase: 7 },
      { path: '/support', label: 'Feedback & Support', description: 'Bugs, feature requests and support tickets', icon: LifeBuoy, permission: 'support.read', phase: 9 },
    ],
  },
  {
    title: 'System management',
    items: [
      { path: '/system', label: 'API & System Health', description: 'Service health, error rates and integrations', icon: Gauge, permission: 'system.read', phase: 9 },
      { path: '/admins', label: 'Admin Users & Roles', description: 'Administrators and role-based access', icon: ShieldCheck, permission: 'admins.manage', phase: 10 },
      { path: '/audit', label: 'Audit Logs', description: 'Every administrative action, who and when', icon: ScrollText, permission: 'audit.read', phase: 10 },
      { path: '/settings', label: 'Application Settings', description: 'Branding, notifications, maintenance mode', icon: Settings, permission: 'settings.read', phase: 10 },
    ],
  },
];

export const NAV_ITEMS: NavItem[] = NAV.flatMap((s) => s.items);

export function findNavItem(pathname: string): NavItem | undefined {
  if (pathname === '/') return NAV_ITEMS[0];
  return NAV_ITEMS.filter((i) => i.path !== '/').find((i) => pathname === i.path || pathname.startsWith(i.path + '/'));
}

export function findSection(item: NavItem): NavSection | undefined {
  return NAV.find((s) => s.items.includes(item));
}

export function searchNav(query: string): NavItem[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  return NAV_ITEMS.filter((i) => i.label.toLowerCase().includes(q) || i.description.toLowerCase().includes(q));
}
