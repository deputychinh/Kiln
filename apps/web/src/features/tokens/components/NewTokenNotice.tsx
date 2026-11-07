import { Button, ButtonVariant, ICON_SIZE, TextField } from '@kiln/ui';
import { Check, Copy as CopyIcon, TriangleAlert } from 'lucide-react';
import { type ReactElement, useEffect, useRef, useState } from 'react';

import { COPIED_FEEDBACK_MS } from '@/constants/auth.constant';
import { useCopy } from '@/hooks/useCopy';
import type { CreatedToken } from '@/interfaces/auth.interface';

import './NewTokenNotice.css';

interface NewTokenNoticeProps {
  token: CreatedToken;
  /** Hides the secret for good. */
  onDone: () => void;
}

type CopyState = 'idle' | 'copied' | 'failed';

/** The one time a token's secret is shown: copy it, then Done forgets it. */
export const NewTokenNotice = ({ token, onDone }: NewTokenNoticeProps): ReactElement => {
  const copy = useCopy();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [copyState, setCopyState] = useState<CopyState>('idle');

  // Focus moves here so the warning and the secret are read first.
  useEffect(() => headingRef.current?.focus(), []);

  // "Copied" fades back to "Copy" (a timer: an outside system).
  useEffect(() => {
    if (copyState !== 'copied') return undefined;
    const timer = window.setTimeout(() => setCopyState('idle'), COPIED_FEEDBACK_MS);
    return () => window.clearTimeout(timer);
  }, [copyState]);

  const copyToken = (): void => {
    navigator.clipboard.writeText(token.token).then(
      () => setCopyState('copied'),
      () => setCopyState('failed'),
    );
  };

  return (
    <section className="new-token-notice" aria-labelledby={`token-${token.id}-title`}>
      <h3
        id={`token-${token.id}-title`}
        className="new-token-notice__title"
        ref={headingRef}
        tabIndex={-1}
      >
        <Check size={ICON_SIZE.sm} aria-hidden="true" />
        {copy.settings.newTitle(token.name)}
      </h3>
      <p className="new-token-notice__warning">
        <TriangleAlert size={ICON_SIZE.sm} aria-hidden="true" />
        {copy.settings.newWarning}
      </p>
      <div className="new-token-notice__value">
        <TextField
          className="new-token-notice__field"
          label={copy.settings.newValue}
          readOnly
          value={token.token}
          spellCheck={false}
          onFocus={(event) => event.target.select()}
        />
        <Button
          variant={ButtonVariant.Secondary}
          className="new-token-notice__copy"
          icon={
            copyState === 'copied' ? (
              <Check size={ICON_SIZE.sm} />
            ) : (
              <CopyIcon size={ICON_SIZE.sm} />
            )
          }
          onClick={copyToken}
        >
          {copyState === 'copied' ? copy.settings.copied : copy.settings.copy}
        </Button>
      </div>
      <p role="status" className="new-token-notice__status">
        {copyState === 'copied' ? copy.settings.copied : null}
        {copyState === 'failed' ? copy.settings.copyFailed : null}
      </p>
      <Button variant={ButtonVariant.Ghost} className="new-token-notice__done" onClick={onDone}>
        {copy.settings.done}
      </Button>
    </section>
  );
};
