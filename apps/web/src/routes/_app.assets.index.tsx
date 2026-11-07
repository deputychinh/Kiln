import { createFileRoute } from '@tanstack/react-router';

import { NoSelection } from '@/features/assets/components/NoSelection';

/** Shown in the detail pane of the expanded layout before anything is selected. */
export const Route = createFileRoute('/_app/assets/')({ component: NoSelection });
