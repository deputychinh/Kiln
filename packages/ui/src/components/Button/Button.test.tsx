import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Button } from '#ui/components/Button/Button';
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
});
