import { render, screen } from '@testing-library/react';

import { AppShell } from '@/components/AppShell/AppShell';

describe('AppShell', () => {
  it('renders the brand, a skip link and the content in the main landmark', () => {
    render(<AppShell>Gallery</AppShell>);

    expect(screen.getByRole('banner')).toHaveTextContent('Kiln');
    expect(screen.getByRole('link', { name: 'Skip to content' })).toHaveAttribute('href', '#main');
    expect(screen.getByRole('main')).toHaveTextContent('Gallery');
  });
});
