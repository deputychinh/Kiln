import type { ReactElement, ReactNode } from 'react';

import { useCopy } from '@/hooks/useCopy';

import './AppShell.css';

interface AppShellProps {
  children: ReactNode;
}

/** Header + main landmark; navigation per window size class arrives with the gallery (KILN-6). */
export const AppShell = ({ children }: AppShellProps): ReactElement => {
  const copy = useCopy();
  return (
    <div className="app-shell">
      <a className="app-shell__skip" href="#main">
        {copy.app.skipToContent}
      </a>
      <header className="app-shell__header">
        <span className="app-shell__brand">{copy.app.name}</span>
      </header>
      <main id="main" className="app-shell__main">
        {children}
      </main>
    </div>
  );
};
