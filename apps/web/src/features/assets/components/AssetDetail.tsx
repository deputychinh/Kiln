import { ErrorState, Skeleton, SkeletonShape } from '@kiln/ui';
import { type ReactElement, useEffect, useRef } from 'react';

import { EXPANDED_MEDIA_QUERY } from '@/constants/layout.constant';
import { BackLink } from '@/features/assets/components/AssetBackLink';
import { AssetBody } from '@/features/assets/components/AssetBody';
import { useAsset } from '@/features/assets/hooks/useAsset';
import { useCopy } from '@/hooks/useCopy';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { describeError, isNotFound } from '@/utils/error.util';

import './AssetDetail.css';

interface AssetDetailProps {
  assetId: string;
}

/** The selected asset: header, actions, preview, versions and facts, with all four states. */
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
        <Skeleton />
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
