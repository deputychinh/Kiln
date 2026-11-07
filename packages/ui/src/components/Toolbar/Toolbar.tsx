import type { ReactElement, ReactNode } from 'react';

import './Toolbar.css';

interface ToolbarProps {
  /** Names the group of controls for assistive technology, e.g. "Gallery options". */
  label: string;
  /** Leading content: a title, a count, filters. */
  children: ReactNode;
  /** Trailing controls, pushed to the end of the row (they wrap below on narrow widths). */
  end?: ReactNode;
}

/** One row of view controls above content: start and end clusters that wrap on narrow widths. */
export const Toolbar = ({ label, children, end }: ToolbarProps): ReactElement => (
  <div className="toolbar" role="group" aria-label={label}>
    <div className="toolbar__start">{children}</div>
    {end ? <div className="toolbar__end">{end}</div> : null}
  </div>
);
