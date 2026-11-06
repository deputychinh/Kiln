import { AssetThumb, Badge, ErrorState, Skeleton, SkeletonShape } from '@kiln/ui';
import { Link } from '@tanstack/react-router';
import { type ReactElement, useEffect, useRef } from 'react';

import { RelativeTime } from '@/components/RelativeTime/RelativeTime';
import { VERSION_STATUS_TONE } from '@/constants/assets.constant';
import { EXPANDED_MEDIA_QUERY } from '@/constants/layout.constant';
import { useAsset } from '@/features/assets/hooks/useAsset';
import { useCopy } from '@/hooks/useCopy';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import type { AssetDetail as AssetDetailData } from '@/interfaces/asset.interface';
import { describeError, isNotFound } from '@/utils/error.util';
import { formatBytes, formatDateTime } from '@/utils/format.util';

import './AssetDetail.css';

interface AssetDetailProps {
  assetId: string;
}

/** Back to the list; `isCompactOnly` hides it when the list is already visible beside the detail. */
const BackLink = ({ isCompactOnly = false }: { isCompactOnly?: boolean }): ReactElement => {
  const copy = useCopy();
  return (
    <Link
      to="/assets"
      className={`asset-detail__back${isCompactOnly ? ' asset-detail__back--compact' : ''}`}
    >
      {copy.assets.back}
    </Link>
  );
};

interface AssetBodyProps {
  asset: AssetDetailData;
  onThumbError: (src: string) => void;
  /** The last refresh failed, so what is shown may be out of date. */
  isStale: boolean;
}

const AssetBody = ({ asset, onThumbError, isStale }: AssetBodyProps): ReactElement => {
  const copy = useCopy();
  const isExpanded = useMediaQuery(EXPANDED_MEDIA_QUERY);
  const headingRef = useRef<HTMLHeadingElement>(null);

  // Below the expanded size class the detail replaces the list, so the focused card is gone:
  // move focus to the heading so keyboard and screen-reader users land on the new content.
  useEffect(() => {
    if (!isExpanded) headingRef.current?.focus();
  }, [isExpanded]);

  const kind = copy.assets.kind[asset.kind];
  const Heading = isExpanded ? 'h2' : 'h1';
  const Subheading = isExpanded ? 'h3' : 'h2';
  return (
    <article className="asset-detail" aria-labelledby="asset-detail-title">
      <BackLink isCompactOnly />
      <AssetThumb
        src={asset.thumbnail_url ?? null}
        alt={copy.assets.previewAlt(asset.name)}
        placeholder={kind}
        onError={onThumbError}
        isEager
      />
      {/* The page's main heading when the detail replaces the list; below the list's h1 otherwise. */}
      <Heading
        id="asset-detail-title"
        className="asset-detail__title"
        ref={headingRef}
        tabIndex={-1}
      >
        {asset.name}
      </Heading>
      {isStale ? (
        <p className="asset-detail__stale" role="status">
          {copy.assets.stale}
        </p>
      ) : null}
      <dl className="asset-detail__facts">
        <dt>{copy.assets.kindLabel}</dt>
        <dd>{kind}</dd>
        <dt>{copy.assets.created}</dt>
        <dd>{formatDateTime(asset.created_at, copy.locale)}</dd>
        <dt>{copy.assets.updated}</dt>
        <dd>
          <RelativeTime iso={asset.updated_at} />
        </dd>
      </dl>
      <Subheading className="asset-detail__subtitle">{copy.assets.versionsTitle}</Subheading>
      <ol className="asset-detail__versions">
        {[...asset.versions].reverse().map((version) => (
          <li key={version.id} className="asset-detail__version">
            <span className="asset-detail__version-head">
              <span className="asset-detail__version-number">
                {copy.assets.versionLabel(version.number)}
              </span>
              <Badge tone={VERSION_STATUS_TONE[version.status]}>
                {copy.assets.status[version.status]}
              </Badge>
            </span>
            <span className="asset-detail__file">
              {copy.assets.fileSummary(
                version.file_name,
                formatBytes(version.size_bytes, copy.locale),
              )}
            </span>
            {version.failure_reason ? (
              <span className="asset-detail__failure">
                {copy.assets.failure[version.failure_reason]}
              </span>
            ) : null}
          </li>
        ))}
      </ol>
    </article>
  );
};

/** The selected asset: preview, facts and versions newest first, with all four states. */
export const AssetDetail = ({ assetId }: AssetDetailProps): ReactElement => {
  const copy = useCopy();
  const { query: asset, reportBrokenThumb } = useAsset(assetId);
  const { refetch } = asset;
  const isExpanded = useMediaQuery(EXPANDED_MEDIA_QUERY);
  const paneRef = useRef<HTMLDivElement>(null);

  // Below the expanded size class the detail replaces the list, so the activated card is gone:
  // focus the pane at once (loading, error and not-found included); the heading takes over
  // once the asset is shown.
  useEffect(() => {
    const pane = paneRef.current;
    // Child effects run first: when the asset is cached, its heading already has focus.
    if (!isExpanded && pane && !pane.contains(document.activeElement)) pane.focus();
  }, [isExpanded]);

  // When the detail replaces the list, its error is the page and names it (the list's h1 is hidden).
  const errorTitleAs = isExpanded ? 'p' : 'h1';
  let content: ReactElement;
  if (asset.isPending) {
    content = (
      <div className="asset-detail" role="status">
        <span className="visually-hidden">{copy.assets.loadingAsset}</span>
        <Skeleton shape={SkeletonShape.Tile} />
        <Skeleton />
        <Skeleton />
      </div>
    );
  } else if (asset.isLoadingError) {
    content = (
      <div className="asset-detail">
        {isNotFound(asset.error) ? (
          <ErrorState
            title={copy.assets.notFoundTitle}
            titleAs={errorTitleAs}
            message={copy.assets.notFoundBody}
            action={<BackLink />}
          />
        ) : (
          <ErrorState
            title={copy.assets.loadAssetFailed}
            titleAs={errorTitleAs}
            message={describeError(asset.error, copy)}
            retryLabel={copy.assets.retry}
            onRetry={() => void refetch()}
            isRetrying={asset.isFetching}
            action={<BackLink />}
          />
        )}
      </div>
    );
  } else {
    content = (
      <AssetBody
        asset={asset.data}
        onThumbError={reportBrokenThumb}
        isStale={asset.isRefetchError}
      />
    );
  }
  return (
    <div className="asset-detail__pane" ref={paneRef} tabIndex={-1}>
      {content}
    </div>
  );
};
