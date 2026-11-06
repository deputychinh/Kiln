import { Button, ButtonVariant, EmptyState, ErrorState, Skeleton, SkeletonShape } from '@kiln/ui';
import type { ReactElement } from 'react';

import { ASSET_PAGE_SIZE, THUMB_REFRESH_MIN_MS } from '@/constants/assets.constant';
import { AssetCard } from '@/features/assets/components/AssetCard';
import { useAssetPages } from '@/features/assets/hooks/useAssetPages';
import { useCopy } from '@/hooks/useCopy';
import { useThrottledCallback } from '@/hooks/useThrottledCallback';
import { describeError } from '@/utils/error.util';

import './AssetGallery.css';

const SKELETON_TILES = Array.from({ length: ASSET_PAGE_SIZE / 3 }, (_, index) => index);

/** The asset grid with its four states and "Load more" pagination. */
export const AssetGallery = (): ReactElement => {
  const copy = useCopy();
  const pages = useAssetPages();
  const { refetch } = pages;
  const refreshThumbs = useThrottledCallback(() => void refetch(), THUMB_REFRESH_MIN_MS);

  const title = <h1 className="asset-gallery__title">{copy.assets.title}</h1>;

  if (pages.isPending) {
    return (
      <div className="asset-gallery" role="status">
        {title}
        <span className="visually-hidden">{copy.assets.loading}</span>
        <div className="asset-gallery__grid">
          {SKELETON_TILES.map((tile) => (
            <Skeleton key={tile} shape={SkeletonShape.Tile} />
          ))}
        </div>
      </div>
    );
  }
  if (pages.isLoadingError) {
    return (
      <div className="asset-gallery">
        {title}
        <ErrorState
          title={copy.assets.loadFailed}
          message={describeError(pages.error, copy)}
          retryLabel={copy.assets.retry}
          onRetry={() => void refetch()}
          isRetrying={pages.isFetching}
        />
      </div>
    );
  }

  const assets = pages.data.pages.flatMap((page) => page.items);
  if (assets.length === 0) {
    return (
      <div className="asset-gallery">
        {title}
        <EmptyState title={copy.assets.emptyTitle}>{copy.assets.emptyBody}</EmptyState>
      </div>
    );
  }
  return (
    <div className="asset-gallery">
      {title}
      <ul className="asset-gallery__grid" aria-label={copy.assets.title}>
        {assets.map((asset) => (
          <li key={asset.id} className="asset-gallery__item">
            <AssetCard asset={asset} onThumbError={refreshThumbs} />
          </li>
        ))}
      </ul>
      <p className="visually-hidden" aria-live="polite">
        {copy.assets.shown(assets.length)}
      </p>
      {pages.isFetchNextPageError ? (
        <ErrorState
          title={copy.assets.loadMoreFailed}
          message={describeError(pages.error, copy)}
          retryLabel={copy.assets.retry}
          onRetry={() => void pages.fetchNextPage()}
          isRetrying={pages.isFetchingNextPage}
        />
      ) : null}
      {pages.hasNextPage && !pages.isFetchNextPageError ? (
        <div className="asset-gallery__more">
          <Button
            variant={ButtonVariant.Secondary}
            // aria-disabled, not disabled: the button keeps focus while the next page loads.
            aria-disabled={pages.isFetchingNextPage}
            onClick={() => {
              if (!pages.isFetchingNextPage) void pages.fetchNextPage();
            }}
          >
            {pages.isFetchingNextPage ? copy.assets.loadingMore : copy.assets.loadMore}
          </Button>
        </div>
      ) : null}
    </div>
  );
};
