import '@testing-library/jest-dom/vitest';

import { configure } from '@testing-library/react';

import { setViewportExpanded } from '@/test/viewport';

// The first render of a file loads its route chunks (code-split) behind the sign-in guard; on a
// busy machine that passes the default 1 s, so findBy* waits up to 3 s (KILN-12).
configure({ asyncUtilTimeout: 3_000 });

// jsdom has no matchMedia; tests choose the window size class through `setViewportExpanded`.
// Each test starts with no stored theme, so the system's (dark unless a test says light) applies.
beforeEach(() => {
  setViewportExpanded(false);
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
});
