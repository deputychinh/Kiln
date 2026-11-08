import { CircleAlert } from 'lucide-react';
import { type ReactElement, type Ref, type TextareaHTMLAttributes, useId } from 'react';

import { ICON_SIZE } from '#ui/constants/icon.constant';

import './TextArea.css';

interface TextAreaProps extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'id'> {
  /** The label (never a placeholder in its place). */
  label: string;
  /** Keeps the label for screen readers only, e.g. a reply field under the comment it answers. */
  isLabelHidden?: boolean;
  /** A short help text under the label, read with the field. */
  hint?: string | undefined;
  /** What is wrong with the value; marks the field invalid and is read with it. */
  error?: string | undefined;
  /** With `maxLength`, shows "used / max" under the field. */
  showCount?: boolean;
  /**
   * The most characters (Unicode code points, as a server counts them) the field takes; typing
   * or pasting stops there. The native attribute counts UTF-16 units, so an emoji would count
   * twice; it is not used.
   */
  maxLength?: number | undefined;
  /** The DOM textarea, e.g. to move focus into it. */
  ref?: Ref<HTMLTextAreaElement> | undefined;
}

/** A labelled multi-line input that grows with its text, with a hint, an error and a count. */
export const TextArea = ({
  label,
  isLabelHidden = false,
  hint,
  error,
  showCount = false,
  className,
  ref,
  maxLength,
  value,
  onChange,
  ...rest
}: TextAreaProps): ReactElement => {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(' ') || undefined;
  const length = typeof value === 'string' ? [...value].length : 0;
  return (
    <div
      className={['text-area', error ? 'text-area--invalid' : '', className ?? ''].join(' ').trim()}
    >
      <label
        className={`text-area__label${isLabelHidden ? ' text-area__label--hidden' : ''}`}
        htmlFor={id}
      >
        {label}
      </label>
      {hint ? (
        <p className="text-area__hint" id={hintId}>
          {hint}
        </p>
      ) : null}
      <textarea
        {...rest}
        ref={ref}
        id={id}
        value={value}
        onChange={(event) => {
          const field = event.currentTarget;
          if (maxLength !== undefined && [...field.value].length > maxLength) {
            field.value = [...field.value].slice(0, maxLength).join('');
          }
          onChange?.(event);
        }}
        className="text-area__input"
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
      />
      {error || (showCount && maxLength !== undefined) ? (
        <div className="text-area__footer">
          {error ? (
            <p className="text-area__error" id={errorId}>
              <CircleAlert size={ICON_SIZE.sm} aria-hidden="true" />
              {error}
            </p>
          ) : null}
          {showCount && maxLength !== undefined ? (
            <span className="text-area__count" aria-hidden="true">
              {length} / {maxLength}
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
};
