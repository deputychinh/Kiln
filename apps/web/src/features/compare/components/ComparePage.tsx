import { AssetThumb, Badge, EmptyState, ErrorState, Skeleton, SkeletonShape } from '@kiln/ui';
import { Link, useNavigate, useSearch } from '@tanstack/react-router';
import { type CSSProperties, type ReactElement, useEffect, useId, useRef, useState } from 'react';

import { RelativeTime } from '@/components/RelativeTime/RelativeTime';
import { VERSION_STATUS_TONE } from '@/constants/assets.constant';
import { COMPARE_ROUTE_ID, SWIPE_START_PERCENT } from '@/constants/compare.constant';
import { CompareMode } from '@/enums/compare-mode.enum';
import { useAsset } from '@/features/assets/hooks/useAsset';
import { useCopy } from '@/hooks/useCopy';
import type { AssetDetail, AssetVersion } from '@/interfaces/asset.interface';
import type { ComparePair } from '@/interfaces/compare.interface';
import { canSwipe, pickPair } from '@/utils/compare.util';
import { describeError, isNotFound } from '@/utils/error.util';
import { formatBytes } from '@/utils/format.util';

import './ComparePage.css';

interface ComparePageProps {
  assetId: string;
}

const BackLink = ({ assetId }: { assetId: string }): ReactElement => {
  const copy = useCopy();
  return (
    <Link to="/assets/$assetId" params={{ assetId }} className="compare-page__back">
      {copy.compare.back}
    </Link>
  );
};

/** One version: its preview (or why there is none) and its facts. */
const VersionPane = ({
  asset,
  version,
  onThumbError,
}: {
  asset: AssetDetail;
  version: AssetVersion;
  onThumbError: (src: string) => void;
}): ReactElement => {
  const copy = useCopy();
  const captionId = useId();
  return (
    <figure className="compare-page__pane" aria-labelledby={captionId}>
      {version.thumbnail_url ? (
        <AssetThumb
          src={version.thumbnail_url}
          alt={copy.compare.previewAlt(version.number)}
          placeholder={copy.assets.kind[asset.kind]}
          onError={onThumbError}
          isEager
        />
      ) : (
        <div className="compare-page__no-preview">{copy.assets.kind[asset.kind]}</div>
      )}
      <figcaption className="compare-page__caption">
        <span className="compare-page__version-head">
          <span id={captionId} className="compare-page__version-number">
            {copy.compare.pane(version.number)}
          </span>
          <Badge tone={VERSION_STATUS_TONE[version.status]}>
            {copy.assets.status[version.status]}
          </Badge>
        </span>
        <span className="compare-page__file">
          {copy.assets.fileSummary(version.file_name, formatBytes(version.size_bytes, copy.locale))}
        </span>
        <RelativeTime iso={version.created_at} />
        {version.failure_reason ? (
          <span className="compare-page__failure">
            {copy.assets.failure[version.failure_reason]}
          </span>
        ) : null}
      </figcaption>
    </figure>
  );
};

/** The right preview over the left one, revealed from the left edge by a slider (or arrow keys). */
const SwipeStage = ({ pair }: { pair: ComparePair }): ReactElement => {
  const copy = useCopy();
  const [reveal, setReveal] = useState(SWIPE_START_PERCENT);
  const { left, right } = pair;
  const style = { '--compare-reveal': `${String(reveal)}%` } as CSSProperties;
  return (
    <div className="compare-page__swipe">
      <div
        className="compare-page__stage"
        role="group"
        aria-label={copy.compare.swipeStage(right.number, left.number)}
        style={style}
      >
        <img
          className="compare-page__layer"
          src={left.thumbnail_url ?? ''}
          alt={copy.compare.previewAlt(left.number)}
        />
        <img
          className="compare-page__layer compare-page__layer--top"
          src={right.thumbnail_url ?? ''}
          alt={copy.compare.previewAlt(right.number)}
        />
      </div>
      <input
        className="compare-page__slider"
        type="range"
        min={0}
        max={100}
        value={reveal}
        aria-label={copy.compare.swipeLabel(right.number, left.number)}
        onChange={(event) => setReveal(Number(event.target.value))}
      />
    </div>
  );
};

const sizeChangeOf = (pair: ComparePair, copy: ReturnType<typeof useCopy>): string => {
  const { left, right } = pair;
  const delta = right.size_bytes - left.size_bytes;
  if (delta === 0) return copy.compare.sameSize(right.number, left.number);
  const size = formatBytes(Math.abs(delta), copy.locale);
  return delta > 0
    ? copy.compare.larger(right.number, size, left.number)
    : copy.compare.smaller(right.number, size, left.number);
};

const CompareBody = ({
  asset,
  pair,
  onThumbError,
}: {
  asset: AssetDetail;
  pair: ComparePair;
  onThumbError: (src: string) => void;
}): ReactElement => {
  const copy = useCopy();
  const search = useSearch({ from: COMPARE_ROUTE_ID });
  const navigate = useNavigate({ from: '/assets/$assetId/compare' });
  const headingRef = useRef<HTMLHeadingElement>(null);
  const swipeAllowed = canSwipe(pair.left, pair.right);
  const mode =
    search.mode === CompareMode.Swipe && swipeAllowed ? CompareMode.Swipe : CompareMode.Side;
  const versions = [...asset.versions].sort((a, b) => b.number - a.number);

  useEffect(() => headingRef.current?.focus(), []);

  /** Choose a version for one side; choosing the other side's version swaps them. */
  const choose = (side: 'left' | 'right', number: number): void => {
    const other = side === 'left' ? pair.right : pair.left;
    const current = side === 'left' ? pair.left : pair.right;
    const next =
      number === other.number
        ? { [side]: number, [side === 'left' ? 'right' : 'left']: current.number }
        : { [side]: number };
    void navigate({
      search: (previous) => ({
        ...previous,
        left: pair.left.number,
        right: pair.right.number,
        ...next,
      }),
    });
  };
  const setMode = (next: CompareMode): void =>
    void navigate({ search: (previous) => ({ ...previous, mode: next }) });

  const picker = (side: 'left' | 'right'): ReactElement => (
    <label className="compare-page__picker">
      <span className="compare-page__picker-label">
        {side === 'left' ? copy.compare.leftLabel : copy.compare.rightLabel}
      </span>
      <select
        className="compare-page__select"
        value={(side === 'left' ? pair.left : pair.right).number}
        onChange={(event) => choose(side, Number(event.target.value))}
      >
        {versions.map((version) => (
          <option key={version.id} value={version.number}>
            {copy.compare.option(version.number, copy.assets.status[version.status])}
          </option>
        ))}
      </select>
    </label>
  );

  return (
    <article className="compare-page" aria-labelledby="compare-title">
      <BackLink assetId={asset.id} />
      <h1 id="compare-title" className="compare-page__title" ref={headingRef} tabIndex={-1}>
        {copy.compare.title(asset.name)}
      </h1>
      <div className="compare-page__controls">
        {picker('left')}
        {picker('right')}
        <fieldset className="compare-page__modes">
          <legend className="compare-page__picker-label">{copy.compare.modeLabel}</legend>
          {[CompareMode.Side, CompareMode.Swipe].map((option) => (
            <label key={option} className="compare-page__mode">
              <input
                type="radio"
                name="compare-mode"
                value={option}
                checked={mode === option}
                disabled={option === CompareMode.Swipe && !swipeAllowed}
                onChange={() => setMode(option)}
              />
              {option === CompareMode.Side ? copy.compare.side : copy.compare.swipe}
            </label>
          ))}
        </fieldset>
      </div>
      {swipeAllowed ? null : <p className="compare-page__note">{copy.compare.swipeUnavailable}</p>}
      {mode === CompareMode.Swipe ? (
        <SwipeStage pair={pair} />
      ) : (
        <div className="compare-page__panes">
          <VersionPane asset={asset} version={pair.left} onThumbError={onThumbError} />
          <VersionPane asset={asset} version={pair.right} onThumbError={onThumbError} />
        </div>
      )}
      <p className="compare-page__size" role="status">
        {sizeChangeOf(pair, copy)}
      </p>
    </article>
  );
};

/** Two versions of an asset side by side, or one swiped over the other; all four states. */
export const ComparePage = ({ assetId }: ComparePageProps): ReactElement => {
  const copy = useCopy();
  const search = useSearch({ from: COMPARE_ROUTE_ID });
  const navigate = useNavigate({ from: '/assets/$assetId/compare' });
  const { query: asset, reportBrokenThumb } = useAsset(assetId);
  const { refetch } = asset;
  const pair = asset.data ? pickPair(asset.data.versions, search) : null;

  // A URL naming versions that do not exist is rewritten in place, never added to history.
  const isCorrected = pair?.isCorrected ?? false;
  const leftNumber = pair?.left.number;
  const rightNumber = pair?.right.number;
  useEffect(() => {
    if (!isCorrected || leftNumber === undefined || rightNumber === undefined) return;
    void navigate({
      search: (previous) => ({ ...previous, left: leftNumber, right: rightNumber }),
      replace: true,
    });
  }, [isCorrected, leftNumber, rightNumber, navigate]);

  if (asset.isPending) {
    return (
      <div className="compare-page" role="status">
        <span className="visually-hidden">{copy.compare.loading}</span>
        <Skeleton shape={SkeletonShape.Tile} />
        <Skeleton />
      </div>
    );
  }
  if (asset.isLoadingError) {
    return (
      <div className="compare-page">
        {isNotFound(asset.error) ? (
          <ErrorState
            title={copy.assets.notFoundTitle}
            titleAs="h1"
            message={copy.assets.notFoundBody}
            action={<Link to="/assets">{copy.assets.back}</Link>}
          />
        ) : (
          <ErrorState
            title={copy.assets.loadAssetFailed}
            titleAs="h1"
            message={describeError(asset.error, copy)}
            retryLabel={copy.assets.retry}
            onRetry={() => void refetch()}
            isRetrying={asset.isFetching}
            action={<BackLink assetId={assetId} />}
          />
        )}
      </div>
    );
  }
  if (!pair) {
    return (
      <div className="compare-page">
        <EmptyState title={copy.compare.fewerTitle} action={<BackLink assetId={assetId} />}>
          {copy.compare.fewerBody}
        </EmptyState>
      </div>
    );
  }
  return <CompareBody asset={asset.data} pair={pair} onThumbError={reportBrokenThumb} />;
};
