import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ErrorState } from '#ui/components/ErrorState/ErrorState';

describe('ErrorState', () => {
  it('is an alert with the title, the message and a retry button', async () => {
    const onRetry = vi.fn();
    render(
      <ErrorState
        title="Could not load assets"
        message="Storage is unavailable."
        retryLabel="Try again"
        onRetry={onRetry}
      />,
    );

    expect(screen.getByRole('alert')).toHaveTextContent('Could not load assets');
    expect(screen.getByRole('alert')).toHaveTextContent('Storage is unavailable.');
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('has no retry button without a handler and shows extra actions', () => {
    render(<ErrorState title="Not found" action={<a href="/assets">Back to assets</a>} />);

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to assets' })).toBeInTheDocument();
  });

  it('keeps the retry button focusable but inert while retrying', async () => {
    const onRetry = vi.fn();
    render(<ErrorState title="Failed" retryLabel="Try again" onRetry={onRetry} isRetrying />);

    const button = screen.getByRole('button', { name: 'Try again' });
    expect(button).toHaveAttribute('aria-disabled', 'true');
    expect(button).toBeEnabled();
    await userEvent.click(button);
    expect(onRetry).not.toHaveBeenCalled();
  });
});
