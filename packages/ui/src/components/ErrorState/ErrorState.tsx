import type { ReactElement, ReactNode } from 'react';

import { Button } from '#ui/components/Button/Button';
import { ButtonVariant } from '#ui/enums/button-variant.enum';

import './ErrorState.css';

interface ErrorStateProps {
  /** What failed, in the person's terms (e.g. the problem `title` from the API). */
  title: string;
  /** Render the title as a heading when the error is the whole page (default: a paragraph). */
  titleAs?: 'p' | 'h1' | 'h2';
  /** Why it failed or what to check, when that helps. */
  message?: string;
  /** The retry button's label; the button shows only when `onRetry` is set too. */
  retryLabel?: string;
  /** Runs the failed request again; the button shows only when `retryLabel` is set too. */
  onRetry?: () => void;
  /** While true, the retry button stays focusable (`aria-disabled`) but does nothing. */
  isRetrying?: boolean;
  /** Another way out when retrying cannot help, e.g. a link back. */
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
