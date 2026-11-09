import { Compass } from 'lucide-react';
import { useNavigate } from 'react-router';
import { Button, Card, EmptyState } from '../components/ui';

export function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <Card>
      <EmptyState
        icon={Compass}
        title="Page not found"
        description="The page you're looking for doesn't exist or has moved."
        action={<Button variant="secondary" onClick={() => navigate('/')}>Back to overview</Button>}
      />
    </Card>
  );
}
