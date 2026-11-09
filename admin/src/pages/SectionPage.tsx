import { Construction } from 'lucide-react';
import type { NavItem } from '../nav';
import { Card, EmptyState, PageHeader } from '../components/ui';

/** Honest placeholder for a section whose backend data arrives in a later phase. No sample numbers. */
export function SectionPage({ item }: { item: NavItem }) {
  return (
    <>
      <PageHeader title={item.label} description={item.description} />
      <Card>
        <EmptyState
          icon={Construction}
          title="Not connected yet"
          description={`This section is wired to live backend data in Phase ${item.phase}. Until then nothing is shown here, so no figure on this dashboard is ever a placeholder.`}
        />
      </Card>
    </>
  );
}
