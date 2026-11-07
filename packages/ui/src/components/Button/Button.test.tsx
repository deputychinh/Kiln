import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Button, buttonClassName } from '#ui/components/Button/Button';
import { ButtonVariant } from '#ui/enums/button-variant.enum';

describe('Button', () => {
  it('is a primary button of type "button" by default', () => {
    render(<Button>Upload</Button>);

    const button = screen.getByRole('button', { name: 'Upload' });
    expect(button).toHaveAttribute('type', 'button');
    expect(button).toHaveClass('button', 'button--primary');
  });

  it('applies the variant modifier and keeps extra class names', () => {
    render(
      <Button variant={ButtonVariant.Ghost} className="toolbar__action">
        Cancel
      </Button>,
    );

    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveClass(
      'button--ghost',
      'toolbar__action',
    );
  });

  it('calls onClick when pressed and not when disabled', async () => {
    const onClick = vi.fn();
    const { rerender } = render(<Button onClick={onClick}>Approve</Button>);

    await userEvent.click(screen.getByRole('button', { name: 'Approve' }));
    rerender(
      <Button onClick={onClick} disabled>
        Approve
      </Button>,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Approve' }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('shows a leading icon that is hidden from assistive technology', () => {
    render(<Button icon={<svg data-testid="icon" />}>Upload</Button>);

    const button = screen.getByRole('button', { name: 'Upload' });
    expect(screen.getByTestId('icon').parentElement).toHaveAttribute('aria-hidden', 'true');
    expect(button).toHaveTextContent('Upload');
  });

  it('gives a link the same look through its class names', () => {
    expect(buttonClassName()).toBe('button button--primary');
    expect(buttonClassName({ variant: ButtonVariant.Secondary, className: 'x' })).toBe(
      'button button--secondary x',
    );
  });
});
