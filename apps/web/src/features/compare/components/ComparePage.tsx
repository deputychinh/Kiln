import {
  EmptyState,
  ErrorState,
  ICON_SIZE,
  SegmentedControl,
  Skeleton,
  SkeletonShape,
} from '@kiln/ui';
import { Link, useNavigate, useSearch } from '@tanstack/react-router';
import { ArrowLeft, Columns2, SplitSquareHorizontal } from 'lucide-react';
import { type ReactElement, useEffect, useRef } from 'react';

import { COMPARE_ROUTE_ID } from '@/constants/compare.constant';
import { CompareMode } from '@/enums/compare-mode.enum';
import { useAsset } from '@/features/assets/hooks/useAsset';
import { SwipeStage } from '@/features/compare/components/SwipeStage';
import { VersionPane } from '@/features/compare/components/VersionPane';
import { useCopy } from '@/hooks/useCopy';
import type { AssetDetail } from '@/interfaces/asset.interface';
import type { ComparePair } from '@/interfaces/compare.interface';
import { canSwipe, isCompareMode, pickPair } from '@/utils/compare.util';
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
      <ArrowLeft size={ICON_SIZE.sm} aria-hidden="true" />
      {copy.compare.back}
    </Link>
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
      <header className="compare-page__header">
        <BackLink assetId={asset.id} />
        <h1 id="compare-title" className="compare-page__title" ref={headingRef} tabIndex={-1}>
          {copy.compare.title(asset.name)}
        </h1>
      </header>
      <div className="compare-page__controls">
        {picker('left')}
        {picker('right')}
        <SegmentedControl<CompareMode>
          label={copy.compare.modeLabel}
          name="compare-mode"
          value={mode}
          options={[
            {
              value: CompareMode.Side,
              label: copy.compare.side,
              icon: <Columns2 size={ICON_SIZE.sm} />,
            },
            {
              value: CompareMode.Swipe,
              label: copy.compare.swipe,
              icon: <SplitSquareHorizontal size={ICON_SIZE.sm} />,
              isDisabled: !swipeAllowed,
            },
          ]}
          onChange={setMode}
        />
      </div>
      {swipeAllowed ? null : <p className="compare-page__note">{copy.compare.swipeUnavailable}</p>}
      {mode === CompareMode.Swipe ? (
        <>
          <SwipeStage pair={pair} onThumbError={onThumbError} />
          <div className="compare-page__panes">
            <VersionPane
              asset={asset}
              version={pair.left}
              onThumbError={onThumbError}
              hasPreview={false}
            />
            <VersionPane
              asset={asset}
              version={pair.right}
              onThumbError={onThumbError}
              hasPreview={false}
            />
          </div>
        </>
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
  // TanStack Router merges the raw params back into the validated ones, so `?mode=diff` arrives
  // here as a string the type calls a mode: check the value, keep only a known mode.
  const mode = isCompareMode(search.mode) ? search.mode : undefined;
  const hasUnknownMode = search.mode !== undefined && mode === undefined;
  const isCorrected = (pair?.isCorrected ?? false) || (pair !== null && hasUnknownMode);
  const leftNumber = pair?.left.number;
  const rightNumber = pair?.right.number;
  useEffect(() => {
    if (!isCorrected || leftNumber === undefined || rightNumber === undefined) return;
    void navigate({
      // From the validated search only: the router's `previous` still carries what was dropped.
      search: { left: leftNumber, right: rightNumber, ...(mode === undefined ? {} : { mode }) },
      replace: true,
    });
  }, [isCorrected, leftNumber, rightNumber, mode, navigate]);

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
