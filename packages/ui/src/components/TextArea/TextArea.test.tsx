import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';

import { TextArea } from '#ui/components/TextArea/TextArea';

const Controlled = ({ maxLength = 10 }: { maxLength?: number }) => {
  const [value, setValue] = useState('');
  return (
    <TextArea
      label="Comment"
      value={value}
      maxLength={maxLength}
      showCount
      onChange={(event) => setValue(event.target.value)}
    />
  );
};

describe('TextArea', () => {
  it('is a multi-line field named by its label that reads its hint', () => {
    render(<TextArea label="Comment" hint="Line breaks are kept." />);

    const field = screen.getByRole('textbox', { name: 'Comment' });
    expect(field.tagName).toBe('TEXTAREA');
    expect(field).toHaveAccessibleDescription('Line breaks are kept.');
    expect(field).not.toHaveAttribute('aria-invalid');
  });

  it('marks itself invalid and reads the error after the hint', () => {
    render(<TextArea label="Comment" hint="Be kind." error="Write a comment first." />);

    const field = screen.getByRole('textbox', { name: 'Comment' });
    expect(field).toHaveAttribute('aria-invalid', 'true');
    expect(field).toHaveAccessibleDescription('Be kind. Write a comment first.');
  });

  it('counts what was typed against the limit and stops at it', async () => {
    render(<Controlled maxLength={5} />);

    await userEvent.type(screen.getByRole('textbox', { name: 'Comment' }), 'abcdefg');

    expect(screen.getByRole('textbox')).toHaveValue('abcde');
    expect(screen.getByText('5 / 5')).toHaveAttribute('aria-hidden', 'true');
  });

  it('stops at the limit in characters (code points), not UTF-16 units, as the API counts', async () => {
    render(<Controlled maxLength={3} />);

    await userEvent.type(screen.getByRole('textbox'), '🎨🎨🎨🎨');

    expect(screen.getByRole('textbox')).toHaveValue('🎨🎨🎨');
    expect(screen.getByText('3 / 3')).toBeInTheDocument();
  });

  it('cuts pasted text at the limit in characters', async () => {
    render(<Controlled maxLength={4} />);
    const field = screen.getByRole('textbox');

    field.focus();
    await userEvent.paste('ab🎨cd🎨');

    expect(field).toHaveValue('ab🎨c');
    expect(field).not.toHaveAttribute('maxlength');
  });

  it('counts an emoji as one character', async () => {
    render(<Controlled />);

    await userEvent.type(screen.getByRole('textbox'), '🎨a');

    expect(screen.getByText('2 / 10')).toBeInTheDocument();
  });

  it('can keep its label for screen readers only', () => {
    render(<TextArea label="Reply" isLabelHidden />);

    expect(screen.getByText('Reply')).toHaveClass('text-area__label--hidden');
    expect(screen.getByRole('textbox', { name: 'Reply' })).toBeInTheDocument();
  });

  it('shows no count without a limit', () => {
    render(<TextArea label="Comment" value="abc" showCount onChange={() => undefined} />);

    expect(screen.queryByText(/\//)).not.toBeInTheDocument();
  });
});
