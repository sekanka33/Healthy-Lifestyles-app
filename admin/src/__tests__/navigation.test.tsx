import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { NAV, NAV_ITEMS, findNavItem, searchNav } from '../nav';
import { makeAdmin, renderAt } from '../test/render';

const sidebar = () => screen.getByRole('complementary', { name: 'Main navigation' });

describe('navigation config', () => {
  it('has the four sections and sixteen pages from the spec, in order', () => {
    expect(NAV.map((s) => s.title)).toEqual([
      'Business management', 'Application management', 'Reporting', 'System management',
    ]);
    expect(NAV_ITEMS.map((i) => i.label)).toEqual([
      'Overview', 'User Management', 'Subscription Management', 'Payments & Revenue', 'Plans & Pricing',
      'Water Tracking', 'Medication Management', 'Fitness Management', 'Notifications & Emails',
      'Analytics', 'Reports', 'Feedback & Support',
      'API & System Health', 'Admin Users & Roles', 'Audit Logs', 'Application Settings',
    ]);
  });

  it('paths and permissions are unique and well-formed', () => {
    const paths = NAV_ITEMS.map((i) => i.path);
    expect(new Set(paths).size).toBe(paths.length);
    for (const i of NAV_ITEMS) {
      expect(i.path).toMatch(/^\/[a-z-]*$/);
      expect(i.permission).toMatch(/^[a-z]+\.[a-z]+$/);
    }
  });

  it('resolves nested paths to their section page', () => {
    expect(findNavItem('/users/123')?.label).toBe('User Management');
    expect(findNavItem('/')?.label).toBe('Overview');
    expect(findNavItem('/nope')).toBeUndefined();
  });

  it('searches labels and descriptions', () => {
    expect(searchNav('refund').map((i) => i.label)).toEqual(['Payments & Revenue']);
    expect(searchNav('   ')).toEqual([]);
  });
});

describe('app shell (signed in as owner)', () => {
  const owner = makeAdmin('owner');

  it('lands on Overview with branding and breadcrumbs', async () => {
    renderAt('/', { admin: owner });
    expect(await screen.findByRole('heading', { level: 1, name: 'Overview' })).toBeInTheDocument();
    expect(within(sidebar()).getByText('LifePulse')).toBeInTheDocument();
    const crumbs = screen.getByRole('navigation', { name: 'Breadcrumb' });
    expect(within(crumbs).getByText('Business management')).toBeInTheDocument();
    expect(within(crumbs).getByText('Overview')).toHaveAttribute('aria-current', 'page');
  });

  it('every sidebar link opens its page and marks it active', async () => {
    const user = userEvent.setup();
    renderAt('/', { admin: owner });
    await screen.findByRole('heading', { level: 1, name: 'Overview' });
    for (const item of NAV_ITEMS) {
      await user.click(within(sidebar()).getByRole('link', { name: item.label }));
      expect(screen.getByRole('heading', { level: 1, name: item.label })).toBeInTheDocument();
      expect(within(sidebar()).getByRole('link', { name: item.label })).toHaveAttribute('aria-current', 'page');
    }
  });

  it('section pages never show sample figures before their phase', async () => {
    renderAt('/payments', { admin: owner });
    expect(await screen.findByText('Not connected yet')).toBeInTheDocument();
    expect(screen.getByText(/Phase 6/)).toBeInTheDocument();
    expect(screen.queryByText(/\$\d/)).not.toBeInTheDocument();
  });

  it('shows a not-found page for unknown routes', async () => {
    renderAt('/does-not-exist', { admin: owner });
    expect(await screen.findByText('Page not found')).toBeInTheDocument();
  });

  it('collapses the sidebar and remembers it', async () => {
    const user = userEvent.setup();
    const { unmount } = renderAt('/', { admin: owner });
    await user.click(await screen.findByRole('button', { name: 'Collapse sidebar' }));
    expect(screen.getByRole('button', { name: 'Expand sidebar' })).toBeInTheDocument();
    unmount();
    renderAt('/', { admin: owner });
    expect(await screen.findByRole('button', { name: 'Expand sidebar' })).toBeInTheDocument();
  });

  it('page search navigates with the keyboard', async () => {
    const user = userEvent.setup();
    renderAt('/', { admin: owner });
    await user.type(await screen.findByRole('combobox', { name: 'Search pages' }), 'audit{Enter}');
    expect(screen.getByRole('heading', { level: 1, name: 'Audit Logs' })).toBeInTheDocument();
  });

  it('page search reports no matches', async () => {
    const user = userEvent.setup();
    renderAt('/', { admin: owner });
    await user.type(await screen.findByRole('combobox', { name: 'Search pages' }), 'zzz');
    expect(screen.getByText(/No pages match/)).toBeInTheDocument();
  });

  it('notifications panel shows an honest empty state', async () => {
    const user = userEvent.setup();
    renderAt('/', { admin: owner });
    await user.click(await screen.findByRole('button', { name: 'Notifications' }));
    expect(screen.getByRole('dialog', { name: 'Notifications' })).toHaveTextContent('No notifications');
  });
});
