import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { AppRoutes } from '../App';

export function renderAt(path = '/') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}
