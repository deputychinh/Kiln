import {
  Badge,
  BadgeTone,
  Button,
  ButtonVariant,
  EmptyState,
  ErrorState,
  ICON_SIZE,
  Skeleton,
  SkeletonShape,
} from '@kiln/ui';
import { KeyRound, Trash2 } from 'lucide-react';
import { type ReactElement, useEffect, useRef, useState } from 'react';

import { RelativeTime } from '@/components/RelativeTime/RelativeTime';
import { useRevokeToken, useTokens } from '@/features/tokens/hooks/useTokens';
import { useCopy } from '@/hooks/useCopy';
import { useNow } from '@/hooks/useNow';
import type { AccessToken } from '@/interfaces/auth.interface';
import { isExpired } from '@/utils/auth.util';
import { describeError } from '@/utils/error.util';
import { formatDateTime } from '@/utils/format.util';

import './TokenList.css';

interface TokenListProps {
  /** Says what happened (a revocation) in the page's status region. */
  onAnnounce: (message: string) => void;
}

const SKELETON_ROWS = 2;

interface RowProps {
  token: AccessToken;
  now: number;
  onAnnounce: (message: string) => void;
}

const TokenRow = ({ token, now, onAnnounce }: RowProps): ReactElement => {
  const copy = useCopy();
  const revoke = useRevokeToken();
  const [isConfirming, setIsConfirming] = useState(false);
  const revokeRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const wasConfirmingRef = useRef(false);
  const expired = isExpired(token, now);

  // Focus follows the inline confirmation: onto "Revoke token", back to "Revoke" on cancel.
  useEffect(() => {
    if (isConfirming) confirmRef.current?.focus();
    else if (wasConfirmingRef.current) revokeRef.current?.focus();
    wasConfirmingRef.current = isConfirming;
  }, [isConfirming]);

  return (
    <li className="token-list__row">
      <div className="token-list__main">
        <p className="token-list__name">
          <KeyRound size={ICON_SIZE.sm} aria-hidden="true" />
          {token.name}
        </p>
        <code className="token-list__prefix">{`${token.prefix}…`}</code>
        <ul className="token-list__badges">
          {token.scopes.map((scope) => (
            <li key={scope}>
              <Badge tone={scope === 'write' ? BadgeTone.Info : BadgeTone.Neutral}>
                {copy.settings.scope[scope]}
              </Badge>
            </li>
          ))}
          {expired ? (
            <li>
              <Badge tone={BadgeTone.Danger}>{copy.settings.expired}</Badge>
            </li>
          ) : null}
        </ul>
      </div>
      <dl className="token-list__facts">
        <div className="token-list__fact">
          <dt className="token-list__term">{copy.settings.created}</dt>
          <dd className="token-list__value">
            <RelativeTime iso={token.created_at} />
          </dd>
        </div>
        <div className="token-list__fact">
          <dt className="token-list__term">{copy.settings.lastUsed}</dt>
          <dd className="token-list__value">
            {token.last_used_at ? (
              <RelativeTime iso={token.last_used_at} />
            ) : (
              copy.settings.neverUsed
            )}
          </dd>
        </div>
        <div className="token-list__fact">
          <dt className="token-list__term">{copy.settings.expires}</dt>
          <dd className="token-list__value">
            <time dateTime={token.expires_at}>{formatDateTime(token.expires_at, copy.locale)}</time>
          </dd>
        </div>
      </dl>
      <div className="token-list__actions">
        {isConfirming ? (
          <div className="token-list__confirm">
            <p className="token-list__confirm-text">{copy.settings.confirmRevoke(token.name)}</p>
            <div className="token-list__confirm-actions">
              <Button
                ref={confirmRef}
                variant={ButtonVariant.Secondary}
                className="token-list__danger"
                aria-disabled={revoke.isPending}
                onClick={() => {
                  if (revoke.isPending) return;
                  revoke.mutate(token.id, {
                    onSuccess: () => onAnnounce(copy.settings.revoked(token.name)),
                  });
                }}
              >
                {revoke.isPending ? copy.settings.revoking : copy.settings.confirm}
              </Button>
              <Button variant={ButtonVariant.Ghost} onClick={() => setIsConfirming(false)}>
                {copy.settings.cancel}
              </Button>
            </div>
            {revoke.isError ? (
              <p role="alert" className="token-list__error">
                {copy.settings.revokeFailed} {describeError(revoke.error, copy)}
              </p>
            ) : null}
          </div>
        ) : (
          <Button
            ref={revokeRef}
            variant={ButtonVariant.Secondary}
            icon={<Trash2 size={ICON_SIZE.sm} />}
            aria-label={copy.settings.revoke(token.name)}
            onClick={() => setIsConfirming(true)}
          >
            {copy.settings.revokeShort}
          </Button>
        )}
      </div>
    </li>
  );
};

/** The person's tokens in all four states; each row revokes after an inline confirmation. */
export const TokenList = ({ onAnnounce }: TokenListProps): ReactElement => {
  const copy = useCopy();
  const tokens = useTokens();
  const now = useNow();

  if (tokens.isPending) {
    return (
      <div className="token-list" aria-busy="true">
        <p className="visually-hidden">{copy.settings.loading}</p>
        {Array.from({ length: SKELETON_ROWS }, (_, index) => (
          <div key={index} className="token-list__skeleton">
            <Skeleton shape={SkeletonShape.Line} />
            <Skeleton shape={SkeletonShape.Line} />
          </div>
        ))}
      </div>
    );
  }
  if (tokens.isError) {
    return (
      <ErrorState
        title={copy.settings.loadFailed}
        message={describeError(tokens.error, copy)}
        retryLabel={copy.settings.retry}
        onRetry={() => void tokens.refetch()}
        isRetrying={tokens.isFetching}
      />
    );
  }
  if (tokens.data.items.length === 0) {
    return (
      <EmptyState
        title={copy.settings.emptyTitle}
        titleAs="h3"
        icon={<KeyRound size={ICON_SIZE.lg} />}
      >
        {copy.settings.emptyBody}
      </EmptyState>
    );
  }
  return (
    <ul className="token-list" aria-label={copy.settings.listLabel}>
      {tokens.data.items.map((token) => (
        <TokenRow key={token.id} token={token} now={now} onAnnounce={onAnnounce} />
      ))}
    </ul>
  );
};
