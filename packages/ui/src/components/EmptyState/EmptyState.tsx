import type { ReactElement, ReactNode } from 'react';

import './EmptyState.css';

interface EmptyStateProps {
  /** Says what is empty (a heading). */
  title: string;
  /** What this place is for and how to fill it. */
  children?: ReactNode;
  /** The first thing to do, usually a primary button. */
  action?: ReactNode;
}

/** Nothing to show yet: what this place is for and what to do first. */
export const EmptyState = ({ title, children, action }: EmptyStateProps): ReactElement => (
  <section className="empty-state">
    <h2 className="empty-state__title">{title}</h2>
    {children ? <p className="empty-state__body">{children}</p> : null}
    {action}
  </section>
);
