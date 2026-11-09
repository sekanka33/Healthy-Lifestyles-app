import { Download, Plus, Users } from 'lucide-react';
import { useState } from 'react';
import { Badge, Button, Card, EmptyState, ErrorState, KpiCard, LoadingState, PageHeader } from '../components/ui';
import { DateRangeFilter, presetRange, type DateRange } from '../components/ui/DateRangeFilter';

/** Design-system reference (not in the sidebar): /ui. Shows components only, never business data. */
export function StyleGuidePage() {
  const [range, setRange] = useState<DateRange>(presetRange('30d'));
  return (
    <>
      <PageHeader
        title="Design system"
        description="Reference for the components every admin page is built from."
        actions={<DateRangeFilter value={range} onChange={setRange} />}
      />
      <p className="mb-4 text-xs text-ink-500">Selected range: {range.from} → {range.to}</p>

      <div className="grid gap-6">
        <Card title="Buttons">
          <div className="flex flex-wrap gap-2">
            <Button icon={Plus}>Primary</Button>
            <Button variant="secondary" icon={Download}>Secondary</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="danger">Danger</Button>
            <Button loading>Saving</Button>
            <Button disabled>Disabled</Button>
          </div>
        </Card>

        <Card title="Badges">
          <div className="flex flex-wrap gap-2">
            <Badge>Neutral</Badge><Badge tone="brand">Active</Badge><Badge tone="warn">Grace period</Badge>
            <Badge tone="bad">Failed</Badge><Badge tone="info">Sandbox</Badge>
          </div>
        </Card>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <KpiCard label="KPI with no data" value={null} hint="An em dash, never a fake zero" icon={Users} />
          <KpiCard label="KPI loading" value={null} loading icon={Users} />
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          <Card title="Empty state"><EmptyState title="No records yet" description="Shown when the backend returns nothing." /></Card>
          <Card title="Error state"><ErrorState message="The server could not be reached." onRetry={() => undefined} /></Card>
          <Card title="Loading state"><LoadingState /></Card>
        </div>
      </div>
    </>
  );
}
