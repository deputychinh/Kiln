import type { ReactElement } from 'react';

import './ProgressBar.css';

interface ProgressBarProps {
  /** Names the bar for assistive technology, e.g. "Uploading rock.png". */
  label: string;
  /** Percent done; kept within 0–100 and rounded to a whole number. */
  value: number;
  /** A readable value when the percent alone says too little, e.g. "4 of 10 MB". */
  valueText?: string;
}

const percentOf = (value: number): number =>
  Number.isFinite(value) ? Math.round(Math.min(100, Math.max(0, value))) : 0;

/** A determinate linear progress indicator (Material 3), announced as a `progressbar`. */
export const ProgressBar = ({ label, value, valueText }: ProgressBarProps): ReactElement => {
  const percent = percentOf(value);
  return (
    <div
      className="progress-bar"
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
      aria-valuetext={valueText}
    >
      <div className="progress-bar__fill" style={{ inlineSize: `${String(percent)}%` }} />
    </div>
  );
};
