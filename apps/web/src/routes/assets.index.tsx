import { createFileRoute } from '@tanstack/react-router';
import type { ReactElement } from 'react';

import { useCopy } from '@/hooks/useCopy';

/** Shown in the detail pane of the expanded layout before anything is selected. */
const NoSelection = (): ReactElement => {
  const copy = useCopy();
  return <p>{copy.assets.selectPrompt}</p>;
};

export const Route = createFileRoute('/assets/')({ component: NoSelection });
