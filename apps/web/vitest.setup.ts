import '@testing-library/jest-dom/vitest';

import { setViewportExpanded } from '@/test/viewport';

// jsdom has no matchMedia; tests choose the window size class through `setViewportExpanded`.
beforeEach(() => setViewportExpanded(false));
