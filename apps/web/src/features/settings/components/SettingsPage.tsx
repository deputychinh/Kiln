import { type ReactElement, useEffect, useRef, useState } from 'react';

import { CreateTokenForm } from '@/features/tokens/components/CreateTokenForm';
import { NewTokenNotice } from '@/features/tokens/components/NewTokenNotice';
import { TokenList } from '@/features/tokens/components/TokenList';
import { useCopy } from '@/hooks/useCopy';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import type { CreatedToken } from '@/interfaces/auth.interface';

import './SettingsPage.css';

/** Account settings; v0.2 holds the personal access tokens for the CLI and Blender (KILN-12). */
export const SettingsPage = (): ReactElement => {
  const copy = useCopy();
  const headingRef = useRef<HTMLHeadingElement>(null);
  // The secret lives only here, in memory, until Done or leaving the page.
  const [created, setCreated] = useState<CreatedToken | null>(null);
  const [announcement, setAnnouncement] = useState('');
  useDocumentTitle(copy.settings.pageTitle);

  useEffect(() => headingRef.current?.focus(), []);

  return (
    <article className="settings-page" aria-labelledby="settings-title">
      <h1 id="settings-title" className="settings-page__title" ref={headingRef} tabIndex={-1}>
        {copy.settings.title}
      </h1>
      <section className="settings-page__section" aria-labelledby="tokens-title">
        <h2 id="tokens-title" className="settings-page__heading">
          {copy.settings.tokensTitle}
        </h2>
        <p className="settings-page__lead">{copy.settings.tokensLead}</p>
        {created ? (
          <NewTokenNotice token={created} onDone={() => setCreated(null)} />
        ) : (
          <CreateTokenForm onCreated={setCreated} />
        )}
        <TokenList onAnnounce={setAnnouncement} />
      </section>
      <p role="status" className="visually-hidden">
        {announcement}
      </p>
    </article>
  );
};
