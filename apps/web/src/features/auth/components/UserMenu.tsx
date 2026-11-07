import { ICON_SIZE } from '@kiln/ui';
import { Link, useNavigate } from '@tanstack/react-router';
import { ChevronDown, LogOut, Settings } from 'lucide-react';
import { type FocusEvent, type ReactElement, useEffect, useId, useRef, useState } from 'react';

import { useMe, useSignOut } from '@/features/auth/hooks/useAuth';
import { useCopy } from '@/hooks/useCopy';
import { initialsOf } from '@/utils/auth.util';

import './UserMenu.css';

/**
 * Who is signed in, in the top bar: a disclosure (WAI-ARIA APG) with the name and email,
 * Settings and Sign out. Escape, a click outside or tabbing away closes it.
 */
export const UserMenu = (): ReactElement | null => {
  const copy = useCopy();
  const navigate = useNavigate();
  const me = useMe();
  const signOut = useSignOut();
  const [isOpen, setIsOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();

  // While open, a click elsewhere closes it and Escape closes it back onto the button
  // (listening to the document: an outside system).
  useEffect(() => {
    if (!isOpen) return undefined;
    const closeOutside = (event: PointerEvent): void => {
      if (event.target instanceof Node && !rootRef.current?.contains(event.target)) {
        setIsOpen(false);
      }
    };
    const closeOnEscape = (event: globalThis.KeyboardEvent): void => {
      if (event.key !== 'Escape') return;
      setIsOpen(false);
      triggerRef.current?.focus();
    };
    document.addEventListener('pointerdown', closeOutside);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('pointerdown', closeOutside);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [isOpen]);

  if (!me.data) return null; // the route guard has loaded it; nothing to show otherwise

  // Tabbing out of the menu closes it.
  const onBlur = (event: FocusEvent<HTMLDivElement>): void => {
    if (!rootRef.current?.contains(event.relatedTarget)) setIsOpen(false);
  };
  const { display_name: name, email } = me.data;

  return (
    <div className="user-menu" ref={rootRef} onBlur={onBlur}>
      <button
        ref={triggerRef}
        type="button"
        className="user-menu__trigger"
        aria-expanded={isOpen}
        aria-controls={panelId}
        onClick={() => setIsOpen((open) => !open)}
      >
        <span className="user-menu__avatar" aria-hidden="true">
          {initialsOf(name)}
        </span>
        <span className="user-menu__name">
          <span className="visually-hidden">{copy.account.menuPrefix}</span> {name}
        </span>
        <ChevronDown className="user-menu__chevron" size={ICON_SIZE.sm} aria-hidden="true" />
      </button>
      <div id={panelId} className="user-menu__panel" hidden={!isOpen}>
        <div className="user-menu__who">
          <p className="user-menu__who-name">{name}</p>
          <p className="user-menu__who-email">{email}</p>
        </div>
        <ul className="user-menu__list">
          <li>
            <Link to="/settings" className="user-menu__item" onClick={() => setIsOpen(false)}>
              <Settings size={ICON_SIZE.sm} aria-hidden="true" />
              {copy.account.settings}
            </Link>
          </li>
          <li>
            <button
              type="button"
              className="user-menu__item"
              aria-disabled={signOut.isPending}
              onClick={() => {
                if (signOut.isPending) return;
                signOut.mutate(undefined, {
                  onSuccess: () => void navigate({ to: '/sign-in', replace: true }),
                });
              }}
            >
              <LogOut size={ICON_SIZE.sm} aria-hidden="true" />
              {signOut.isPending ? copy.account.signingOut : copy.account.signOut}
            </button>
          </li>
        </ul>
        <div role="alert" className="user-menu__alert">
          {signOut.isError ? copy.account.signOutFailed : null}
        </div>
      </div>
    </div>
  );
};
