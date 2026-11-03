import { createFileRoute } from '@tanstack/react-router';
import type { ReactElement } from 'react';

import { ApiStatus } from '@/features/health/components/ApiStatus';
import { useCopy } from '@/hooks/useCopy';

const Home = (): ReactElement => {
  const copy = useCopy();
  return (
    <>
      <h1>{copy.app.name}</h1>
      <p>{copy.app.tagline}</p>
      <ApiStatus />
    </>
  );
};

export const Route = createFileRoute('/')({ component: Home });
