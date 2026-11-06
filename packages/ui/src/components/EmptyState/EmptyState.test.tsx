import { render, screen } from '@testing-library/react';

import { EmptyState } from '#ui/components/EmptyState/EmptyState';

describe('EmptyState', () => {
  it('names the situation as a heading and says what to do next', () => {
    render(
      <EmptyState title="No assets yet" action={<a href="/docs">Read how</a>}>
        Publish one from the CLI.
      </EmptyState>,
    );

    expect(screen.getByRole('heading', { name: 'No assets yet' })).toBeInTheDocument();
    expect(screen.getByText('Publish one from the CLI.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Read how' })).toBeInTheDocument();
  });
});
