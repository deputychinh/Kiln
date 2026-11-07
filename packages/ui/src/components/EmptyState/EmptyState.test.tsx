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

  it('can be the page heading and shows a decorative icon', () => {
    render(
      <EmptyState title="Nothing to compare yet" titleAs="h1" icon={<svg data-testid="icon" />} />,
    );

    expect(
      screen.getByRole('heading', { level: 1, name: 'Nothing to compare yet' }),
    ).toBeInTheDocument();
    expect(screen.getByTestId('icon').parentElement).toHaveAttribute('aria-hidden', 'true');
  });
});
