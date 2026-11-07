import { render, screen } from '@testing-library/react';

import { Badge } from '#ui/components/Badge/Badge';
import { BadgeTone } from '#ui/enums/badge-tone.enum';

describe('Badge', () => {
  it('shows its label as text with the neutral tone by default', () => {
    render(<Badge>Image</Badge>);

    expect(screen.getByText('Image')).toHaveClass('badge', 'badge--neutral');
  });

  it('applies the tone modifier so colour is never the only signal', () => {
    render(<Badge tone={BadgeTone.Danger}>Failed</Badge>);

    expect(screen.getByText('Failed')).toHaveClass('badge--danger');
  });

  it('shows a decorative leading icon', () => {
    render(<Badge icon={<svg data-testid="icon" />}>Model</Badge>);

    expect(screen.getByText('Model')).toContainElement(screen.getByTestId('icon'));
    expect(screen.getByTestId('icon').parentElement).toHaveAttribute('aria-hidden', 'true');
  });
});
