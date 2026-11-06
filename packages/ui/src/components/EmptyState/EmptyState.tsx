import type { ReactElement, ReactNode } from 'react';

import './EmptyState.css';

interface EmptyStateProps {
  title: string;
  children?: ReactNode;
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
