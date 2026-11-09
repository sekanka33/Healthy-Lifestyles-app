import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { Button, ErrorState, KpiCard } from '../components/ui';
import { DateRangeFilter, presetRange, validateRange, type DateRange } from '../components/ui/DateRangeFilter';

describe('KpiCard', () => {
  it('shows an em dash, not zero, when there is no data', () => {
    render(<KpiCard label="MRR" value={null} />);
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.queryByText('0')).not.toBeInTheDocument();
  });

  it('shows the value and hint', () => {
    render(<KpiCard label="Users" value="1,204" hint="+12 this week" />);
    expect(screen.getByText('1,204')).toBeInTheDocument();
    expect(screen.getByText('+12 this week')).toBeInTheDocument();
  });
});

describe('Button', () => {
  it('is disabled and not clickable while loading', async () => {
    const onClick = vi.fn();
    render(<Button loading onClick={onClick}>Save</Button>);
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(onClick).not.toHaveBeenCalled();
  });
});

describe('ErrorState', () => {
  it('retries', async () => {
    const onRetry = vi.fn();
    render(<ErrorState message="Down" onRetry={onRetry} />);
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});

describe('date ranges', () => {
  const today = new Date(2026, 10, 9); // 9 Nov 2026

  it('builds inclusive preset ranges', () => {
    expect(presetRange('today', today)).toEqual({ preset: 'today', from: '2026-11-09', to: '2026-11-09' });
    expect(presetRange('7d', today)).toEqual({ preset: '7d', from: '2026-11-03', to: '2026-11-09' });
    expect(presetRange('90d', today).from).toBe('2026-08-12');
  });

  it('validates custom ranges', () => {
    expect(validateRange('', '2026-11-01', today)).toMatch(/both/);
    expect(validateRange('2026-11-05', '2026-11-01', today)).toMatch(/on or before/);
    expect(validateRange('2026-11-01', '2026-11-10', today)).toMatch(/future/);
    expect(validateRange('2024-01-01', '2026-11-01', today)).toMatch(/at most 366/);
    expect(validateRange('2026-01-01', '2026-11-09', today)).toBeNull();
  });

  function Harness({ onChange }: { onChange: (r: DateRange) => void }) {
    const [range, setRange] = useState(presetRange('30d'));
    return <DateRangeFilter value={range} onChange={(r) => { setRange(r); onChange(r); }} />;
  }

  it('switches presets', async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    await userEvent.click(screen.getByRole('button', { name: 'Last 7 days' }));
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ preset: '7d' }));
    expect(screen.getByRole('button', { name: 'Last 7 days' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('rejects an invalid custom range without calling onChange', async () => {
    const onChange = vi.fn();
    const { container } = render(<Harness onChange={onChange} />);
    await userEvent.click(screen.getByRole('button', { name: /Custom/ }));
    const [from, to] = container.querySelectorAll<HTMLInputElement>('input[type="date"]');
    await userEvent.clear(from);
    await userEvent.type(from, '2026-11-05');
    await userEvent.clear(to);
    await userEvent.type(to, '2026-11-01');
    await userEvent.click(screen.getByRole('button', { name: 'Apply' }));
    expect(screen.getByRole('alert')).toHaveTextContent(/on or before/);
    expect(onChange).not.toHaveBeenCalled();
  });
});
