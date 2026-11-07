import type { ReactNode } from 'react';

/** One tab of `Tabs` and the panel it shows. */
export interface TabItem {
  /** Stable within the tab list; also used in the URL by callers that keep the tab there. */
  id: string;
  label: string;
  /** A short count or status after the label (part of the tab's name). */
  badge?: ReactNode;
  panel: ReactNode;
}
