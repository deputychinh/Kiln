import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { TextField } from '#ui/components/TextField/TextField';

describe('TextField', () => {
  it('is named by its label and reads its hint', () => {
    render(<TextField label="Email" hint="The address your studio gave you." type="email" />);

    const input = screen.getByRole('textbox', { name: 'Email' });
    expect(input).toHaveAccessibleDescription('The address your studio gave you.');
    expect(input).not.toHaveAttribute('aria-invalid');
  });

  it('marks itself invalid and reads the error after the hint', () => {
    render(<TextField label="Name" hint="Shown in the list." error="Enter a name." />);

    const input = screen.getByRole('textbox', { name: 'Name' });
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAccessibleDescription('Shown in the list. Enter a name.');
  });

  it('passes typing through to the native input', async () => {
    const onChange = vi.fn();
    render(<TextField label="Name" onChange={onChange} />);

    await userEvent.type(screen.getByRole('textbox', { name: 'Name' }), 'CLI');

    expect(onChange).toHaveBeenCalledTimes(3);
  });

  it('keeps two fields apart with their own ids', () => {
    render(
      <>
        <TextField label="One" error="Bad one" />
        <TextField label="Two" error="Bad two" />
      </>,
    );

    expect(screen.getByRole('textbox', { name: 'Two' })).toHaveAccessibleDescription('Bad two');
  });
});
