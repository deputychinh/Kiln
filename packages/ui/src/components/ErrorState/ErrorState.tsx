import type { ReactElement, ReactNode } from 'react';

import { Button } from '#ui/components/Button/Button';
import { ButtonVariant } from '#ui/enums/button-variant.enum';

import './ErrorState.css';

interface ErrorStateProps {
  title: string;
  /** Render the title as a heading when the error is the whole page (default: a paragraph). */
  titleAs?: 'p' | 'h1' | 'h2';
  message?: string;
  retryLabel?: string;
  onRetry?: () => void;
  isRetrying?: boolean;
  action?: ReactNode;
}

/** What failed and the way out: retry when it can help, another action otherwise. */
export const ErrorState = ({
  title,
  titleAs: Title = 'p',
  message,
  retryLabel,
  onRetry,
  isRetrying = false,
  action,
}: ErrorStateProps): ReactElement => (
  <div className="error-state" role="alert">
    <Title className="error-state__title">{title}</Title>
    {message ? <p className="error-state__message">{message}</p> : null}
    <div className="error-state__actions">
      {onRetry && retryLabel ? (
        <Button
          variant={ButtonVariant.Secondary}
          // aria-disabled, not disabled: the button keeps focus while the retry runs.
          aria-disabled={isRetrying}
          onClick={() => {
            if (!isRetrying) onRetry();
          }}
        >
          {retryLabel}
        </Button>
      ) : null}
      {action}
    </div>
  </div>
);
