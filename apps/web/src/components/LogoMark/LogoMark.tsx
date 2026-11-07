import type { ReactElement } from 'react';

import './LogoMark.css';

/** Kiln's mark: a kiln's arched mouth with a flame inside (decorative; the wordmark names it). */
export const LogoMark = (): ReactElement => (
  <svg className="logo-mark" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
    <rect className="logo-mark__tile" width="32" height="32" rx="8" />
    <path className="logo-mark__kiln" d="M7 26V15a9 9 0 0 1 18 0v11h-4V15a5 5 0 0 0-10 0v11H7Z" />
    <path
      className="logo-mark__flame"
      d="M16 26c-2.6 0-4-1.7-4-3.8 0-2.4 2-3.5 2.6-5.7.9 1 1 2 .8 3 .9-.4 1.6-1.4 1.8-2.6 1.7 1.5 2.8 3.2 2.8 5.3 0 2.1-1.4 3.8-4 3.8Z"
    />
  </svg>
);
