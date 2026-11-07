import type { ReactElement, ReactNode } from 'react';

import './EmptyState.css';

interface EmptyStateProps {
  /** Says what is empty (a heading). */
  title: string;
  /** The heading level: h2 inside a page (default), h1 when the empty state is the page. */
  titleAs?: 'h1' | 'h2' | 'h3';
  /** A decorative icon above the title. */
  icon?: ReactNode;
  /** What this place is for and how to fill it. */
  children?: ReactNode;
  /** The first thing to do, usually a primary button. */
  action?: ReactNode;
}

/** Nothing to show yet: what this place is for and what to do first. */
export const EmptyState = ({
  title,
  titleAs: Title = 'h2',
  icon,
  children,
  action,
}: EmptyStateProps): ReactElement => (
  <section className="empty-state">
    {icon ? (
      <span className="empty-state__icon" aria-hidden="true">
        {icon}
      </span>
    ) : null}
    <Title className="empty-state__title">{title}</Title>
    {children ? <p className="empty-state__body">{children}</p> : null}
    {action ? <div className="empty-state__action">{action}</div> : null}
  </section>
);
