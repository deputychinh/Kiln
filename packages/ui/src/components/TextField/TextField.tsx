import { CircleAlert } from 'lucide-react';
import { type InputHTMLAttributes, type ReactElement, type Ref, useId } from 'react';

import { ICON_SIZE } from '#ui/constants/icon.constant';

import './TextField.css';

interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> {
  /** The visible label (never a placeholder in its place). */
  label: string;
  /** A short help text under the label, read with the field. */
  hint?: string | undefined;
  /** What is wrong with the value; marks the field invalid and is read with it. */
  error?: string | undefined;
  /** The DOM input, e.g. to move focus to the first invalid field. */
  ref?: Ref<HTMLInputElement> | undefined;
}

/** A labelled single-line input with an optional hint and an error tied to it (WCAG 3.3.1). */
export const TextField = ({
  label,
  hint,
  error,
  className,
  ref,
  ...rest
}: TextFieldProps): ReactElement => {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(' ') || undefined;
  return (
    <div
      className={['text-field', error ? 'text-field--invalid' : '', className ?? '']
        .join(' ')
        .trim()}
    >
      <label className="text-field__label" htmlFor={id}>
        {label}
      </label>
      {hint ? (
        <p className="text-field__hint" id={hintId}>
          {hint}
        </p>
      ) : null}
      <input
        {...rest}
        ref={ref}
        id={id}
        className="text-field__input"
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
      />
      {error ? (
        <p className="text-field__error" id={errorId}>
          <CircleAlert size={ICON_SIZE.sm} aria-hidden="true" />
          {error}
        </p>
      ) : null}
    </div>
  );
};
