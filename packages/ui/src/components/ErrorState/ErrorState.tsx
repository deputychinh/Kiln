import type { ReactElement, ReactNode } from 'react';

import { Button } from '#ui/components/Button/Button';
import { ButtonVariant } from '#ui/enums/button-variant.enum';

import './ErrorState.css';

interface ErrorStateProps {
  title: string;
  message?: string;
  retryLabel?: string;
  onRetry?: () => void;
  isRetrying?: boolean;
  action?: ReactNode;
}

/** What failed and the way out: retry when it can help, another action otherwise. */
export const ErrorState = ({
  title,
  message,
  retryLabel,
  onRetry,
  isRetrying = false,
  action,
}: ErrorStateProps): ReactElement => (
  <div className="error-state" role="alert">
    <p className="error-state__title">{title}</p>
    {message ? <p className="error-state__message">{message}</p> : null}
    <div className="error-state__actions">
      {onRetry && retryLabel ? (
        <Button variant={ButtonVariant.Secondary} onClick={onRetry} disabled={isRetrying}>
          {retryLabel}
        </Button>
      ) : null}
      {action}
    </div>
  </div>
);
