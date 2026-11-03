import { Button, ButtonVariant } from '@kiln/ui';
import type { ReactElement } from 'react';

import { useApiHealth } from '@/features/health/hooks/useApiHealth';
import { useCopy } from '@/hooks/useCopy';

import './ApiStatus.css';

/** Shows whether the API answers; the first end-to-end slice of the walking skeleton. */
export const ApiStatus = (): ReactElement => {
  const copy = useCopy();
  const health = useApiHealth();

  if (health.isPending) {
    return (
      <p className="api-status" role="status">
        {copy.health.checking}
      </p>
    );
  }
  if (health.isError) {
    return (
      <div className="api-status api-status--down" role="alert">
        <span className="api-status__dot" aria-hidden="true" />
        <span>{copy.health.down}</span>
        <Button variant={ButtonVariant.Secondary} onClick={() => void health.refetch()}>
          {copy.health.retry}
        </Button>
      </div>
    );
  }
  return (
    <p className="api-status api-status--ok" role="status">
      <span className="api-status__dot" aria-hidden="true" />
      {copy.health.ok(health.data.version)}
    </p>
  );
};
