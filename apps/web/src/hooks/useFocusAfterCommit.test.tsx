import { act, render, screen } from '@testing-library/react';
import { type ReactElement, useCallback, useRef, useState } from 'react';

import { useFocusAfterCommit } from '@/hooks/useFocusAfterCommit';

const Field = (): ReactElement => {
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLInputElement>(null);
  const focus = useCallback(() => ref.current?.focus(), []);
  const requestFocus = useFocusAfterCommit(focus);
  return (
    <>
      <input ref={ref} aria-label="Name" aria-invalid={error ? true : undefined} />
      <button
        type="button"
        onClick={() => {
          setError('Required');
          requestFocus();
        }}
      >
        Save
      </button>
    </>
  );
};

describe('useFocusAfterCommit', () => {
  it('focuses after the state set with it is in the DOM, and again on every request', () => {
    render(<Field />);
    const field = screen.getByRole('textbox', { name: 'Name' });
    const seen: (string | null)[] = [];
    field.addEventListener('focusin', () => seen.push(field.getAttribute('aria-invalid')));
    const save = screen.getByRole('button', { name: 'Save' });

    expect(field).not.toHaveFocus();
    act(() => save.click());
    expect(field).toHaveFocus();
    save.focus();
    act(() => save.click());

    expect(field).toHaveFocus();
    expect(seen).toEqual(['true', 'true']);
  });
});
