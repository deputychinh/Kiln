import { AssetThumb, Badge, ErrorState, Skeleton, SkeletonShape } from '@kiln/ui';
import { Link } from '@tanstack/react-router';
import { type ReactElement, useEffect, useRef } from 'react';

import { RelativeTime } from '@/components/RelativeTime/RelativeTime';
import { THUMB_REFRESH_MIN_MS, VERSION_STATUS_TONE } from '@/constants/assets.constant';
import { EXPANDED_MEDIA_QUERY } from '@/constants/layout.constant';
import { useAsset } from '@/features/assets/hooks/useAsset';
import { useCopy } from '@/hooks/useCopy';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { useThrottledCallback } from '@/hooks/useThrottledCallback';
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
  onThumbError: () => void;
}

const AssetBody = ({ asset, onThumbError }: AssetBodyProps): ReactElement => {
  const copy = useCopy();
  const isExpanded = useMediaQuery(EXPANDED_MEDIA_QUERY);
  const headingRef = useRef<HTMLHeadingElement>(null);

  // Below the expanded size class the detail replaces the list, so the focused card is gone:
  // move focus to the heading so keyboard and screen-reader users land on the new content.
  useEffect(() => {
    if (!isExpanded) headingRef.current?.focus();
  }, [asset.id, isExpanded]);

  const kind = copy.assets.kind[asset.kind];
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
      <h2 id="asset-detail-title" className="asset-detail__title" ref={headingRef} tabIndex={-1}>
        {asset.name}
      </h2>
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
      <h3 className="asset-detail__subtitle">{copy.assets.versionsTitle}</h3>
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
              {version.file_name} · {formatBytes(version.size_bytes, copy.locale)}
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
  const asset = useAsset(assetId);
  const { refetch } = asset;
  const refreshThumb = useThrottledCallback(() => void refetch(), THUMB_REFRESH_MIN_MS);

  if (asset.isPending) {
    return (
      <div className="asset-detail" role="status">
        <span className="visually-hidden">{copy.assets.loadingAsset}</span>
        <Skeleton shape={SkeletonShape.Tile} />
        <Skeleton />
        <Skeleton />
      </div>
    );
  }
  if (asset.isLoadingError) {
    return (
      <div className="asset-detail">
        {isNotFound(asset.error) ? (
          <ErrorState
            title={copy.assets.notFoundTitle}
            message={copy.assets.notFoundBody}
            action={<BackLink />}
          />
        ) : (
          <ErrorState
            title={copy.assets.loadAssetFailed}
            message={describeError(asset.error, copy)}
            retryLabel={copy.assets.retry}
            onRetry={() => void refetch()}
            isRetrying={asset.isFetching}
            action={<BackLink />}
          />
        )}
      </div>
    );
  }
  return <AssetBody asset={asset.data} onThumbError={refreshThumb} />;
};
