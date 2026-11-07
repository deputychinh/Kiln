import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { IconButton } from '#ui/components/IconButton/IconButton';
import { ButtonVariant } from '#ui/enums/button-variant.enum';
import { IconButtonSize } from '#ui/enums/icon-button-size.enum';

describe('IconButton', () => {
  it('is named by its label, which also shows as a tooltip without being read twice', () => {
    render(<IconButton label="Switch to light theme" icon={<svg />} />);

    const button = screen.getByRole('button', { name: 'Switch to light theme' });
    expect(button).toHaveAttribute('type', 'button');
    expect(button).toHaveClass('icon-button', 'icon-button--ghost', 'icon-button--medium');
    const tooltip = screen.getByRole('tooltip', { hidden: true });
    expect(tooltip).toHaveTextContent('Switch to light theme');
    expect(tooltip).toHaveAttribute('aria-hidden', 'true');
  });

  it('takes the variant and size modifiers and reports a toggle state', () => {
    render(
      <IconButton
        label="Compact grid"
        icon={<svg />}
        variant={ButtonVariant.Secondary}
        size={IconButtonSize.Small}
        isPressed
      />,
    );

    const button = screen.getByRole('button', { name: 'Compact grid' });
    expect(button).toHaveClass('icon-button--secondary', 'icon-button--small');
    expect(button).toHaveAttribute('aria-pressed', 'true');
  });

  it('calls onClick when pressed, and not when disabled', async () => {
    const onClick = vi.fn();
    const { rerender } = render(<IconButton label="Zoom in" icon={<svg />} onClick={onClick} />);

    await userEvent.click(screen.getByRole('button', { name: 'Zoom in' }));
    rerender(<IconButton label="Zoom in" icon={<svg />} onClick={onClick} disabled />);
    await userEvent.click(screen.getByRole('button', { name: 'Zoom in' }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
