import { render, screen } from '@testing-library/react';

import { StatusDot } from '#ui/components/StatusDot/StatusDot';
import { BadgeTone } from '#ui/enums/badge-tone.enum';

describe('StatusDot', () => {
  it('says the status in words next to a decorative dot', () => {
    const { container } = render(<StatusDot tone={BadgeTone.Success}>Ready</StatusDot>);

    expect(screen.getByText('Ready')).toHaveClass('status-dot', 'status-dot--success');
    expect(container.querySelector('.status-dot__dot')).toHaveAttribute('aria-hidden', 'true');
  });

  it('is neutral and still by default, and pulses for work in progress', () => {
    const { rerender } = render(<StatusDot>Queued</StatusDot>);
    expect(screen.getByText('Queued')).toHaveClass('status-dot--neutral');
    expect(screen.getByText('Queued')).not.toHaveClass('status-dot--active');

    rerender(
      <StatusDot tone={BadgeTone.Info} isActive>
        Processing
      </StatusDot>,
    );
    expect(screen.getByText('Processing')).toHaveClass('status-dot--info', 'status-dot--active');
  });
});
