import '@testing-library/jest-dom/vitest';

import { setViewportExpanded } from '@/test/viewport';

// jsdom has no matchMedia; tests choose the window size class through `setViewportExpanded`.
// Each test starts with no stored theme, so the system's (dark unless a test says light) applies.
beforeEach(() => {
  setViewportExpanded(false);
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
});
