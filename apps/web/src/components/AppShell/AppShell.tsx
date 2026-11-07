import { ICON_SIZE } from '@kiln/ui';
import { Link } from '@tanstack/react-router';
import { Images, Search } from 'lucide-react';
import { type ReactElement, type ReactNode, useId } from 'react';

import { LogoMark } from '@/components/LogoMark/LogoMark';
import { ThemeToggle } from '@/components/ThemeToggle/ThemeToggle';
import { useCopy } from '@/hooks/useCopy';

import './AppShell.css';

interface AppShellProps {
  /** Page-wide actions in the top bar, before the theme switch (e.g. Upload). */
  actions?: ReactNode;
  /** Fixed layers that belong to the whole app (the upload tray, the drop overlay). */
  overlays?: ReactNode;
  children: ReactNode;
}

/**
 * The app frame (Material 3 adaptive): a top bar with the brand, search and actions; navigation
 * as a bottom bar on compact screens, a rail from 600 px and a sidebar from 1200 px.
 */
export const AppShell = ({ actions, overlays, children }: AppShellProps): ReactElement => {
  const copy = useCopy();
  const searchId = useId();
  return (
    <div className="app-shell">
      <a className="app-shell__skip" href="#main">
        {copy.app.skipToContent}
      </a>
      <header className="app-shell__bar">
        <Link to="/assets" className="app-shell__brand">
          <LogoMark />
          <span className="app-shell__wordmark">{copy.app.name}</span>
        </Link>
        {/* Search arrives with KILN-15; the field is in place so the bar does not move then. */}
        <form
          className="app-shell__search"
          role="search"
          aria-label={copy.app.searchLabel}
          onSubmit={(event) => event.preventDefault()}
        >
          <Search className="app-shell__search-icon" size={ICON_SIZE.sm} aria-hidden="true" />
          <label className="visually-hidden" htmlFor={searchId}>
            {copy.app.searchLabel}
          </label>
          <input
            id={searchId}
            className="app-shell__search-input"
            type="search"
            placeholder={copy.app.searchPlaceholder}
            aria-describedby={`${searchId}-note`}
            autoComplete="off"
          />
          <span id={`${searchId}-note`} className="visually-hidden">
            {copy.app.searchNote}
          </span>
        </form>
        <div className="app-shell__actions">
          {actions}
          <ThemeToggle />
        </div>
      </header>
      <nav className="app-shell__nav" aria-label={copy.app.navLabel}>
        <ul className="app-shell__nav-list">
          <li>
            <Link to="/assets" className="app-shell__nav-item">
              <span className="app-shell__nav-icon" aria-hidden="true">
                <Images size={ICON_SIZE.md} />
              </span>
              <span className="app-shell__nav-label">{copy.app.navAssets}</span>
            </Link>
          </li>
        </ul>
      </nav>
      <main id="main" className="app-shell__main" tabIndex={-1}>
        {children}
      </main>
      {overlays}
    </div>
  );
};
