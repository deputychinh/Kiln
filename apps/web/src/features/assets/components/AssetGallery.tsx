import { Button, ButtonVariant, EmptyState, ErrorState, Skeleton, SkeletonShape } from '@kiln/ui';
import { type ReactElement, useEffect, useRef, useState } from 'react';

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
  const galleryRef = useRef<HTMLDivElement>(null);
  // After "Load more": the index of the first new card, or 'error' for the retry button.
  const [focusAfterLoad, setFocusAfterLoad] = useState<number | 'error' | null>(null);

  // "Load more" disappears on the last page and is replaced by an error on failure; either way
  // move focus somewhere useful (once the new cards are rendered) instead of the page body.
  useEffect(() => {
    if (focusAfterLoad === null || !galleryRef.current) return;
    const target =
      focusAfterLoad === 'error'
        ? galleryRef.current.querySelector<HTMLElement>('[role="alert"] button')
        : galleryRef.current.querySelectorAll<HTMLElement>('.asset-card')[focusAfterLoad];
    target?.focus();
    setFocusAfterLoad(null);
  }, [focusAfterLoad]);
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
  const loadMore = async (): Promise<void> => {
    const shownBefore = assets.length;
    const result = await pages.fetchNextPage();
    setFocusAfterLoad(result.isError ? 'error' : shownBefore);
  };

  return (
    <div className="asset-gallery" ref={galleryRef}>
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
          onRetry={() => void loadMore()}
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
              if (!pages.isFetchingNextPage) void loadMore();
            }}
          >
            {pages.isFetchingNextPage ? copy.assets.loadingMore : copy.assets.loadMore}
          </Button>
        </div>
      ) : null}
    </div>
  );
};
