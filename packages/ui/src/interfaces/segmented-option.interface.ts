import type { ReactNode } from 'react';

/** One choice of a `SegmentedControl`. */
export interface SegmentedOption<Value extends string> {
  value: Value;
  /** The choice in words; with `isIconOnly` it is the accessible name only. */
  label: string;
  /** A leading icon (decorative). */
  icon?: ReactNode;
  /** The choice cannot be made right now (say why nearby). */
  isDisabled?: boolean;
}
