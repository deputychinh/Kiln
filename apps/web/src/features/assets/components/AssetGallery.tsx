import {
  Button,
  ButtonVariant,
  EmptyState,
  ErrorState,
  ICON_SIZE,
  SegmentedControl,
  Skeleton,
  SkeletonShape,
  Toolbar,
} from '@kiln/ui';
import { useNavigate, useSearch } from '@tanstack/react-router';
import { ArrowDownUp, Box, Grid2x2, Grid3x3, Image, Images, ListFilter } from 'lucide-react';
import { type ReactElement, type ReactNode, useCallback, useEffect, useRef, useState } from 'react';

import {
  ASSET_LIST_QUERY_KEY,
  ASSET_PAGE_SIZE,
  THUMB_REFRESH_WINDOW_MS,
} from '@/constants/assets.constant';
import { REVIEW_STATES } from '@/constants/reviews.constant';
import { CardSize } from '@/enums/card-size.enum';
import { GallerySort } from '@/enums/gallery-sort.enum';
import { AssetCard } from '@/features/assets/components/AssetCard';
import { useAssetPages } from '@/features/assets/hooks/useAssetPages';
import { UploadButton } from '@/features/uploads/components/UploadButton';
import { useCopy } from '@/hooks/useCopy';
import { useKeyedThrottle } from '@/hooks/useKeyedThrottle';
import type { AssetKind } from '@/interfaces/asset.interface';
import type { GallerySearch } from '@/interfaces/gallery.interface';
import type { ReviewState } from '@/interfaces/review.interface';
import { describeError } from '@/utils/error.util';
import { isFiltered, parseGallerySearch, visibleAssets, withOption } from '@/utils/gallery.util';

import './AssetGallery.css';

const SKELETON_CARDS = Array.from({ length: ASSET_PAGE_SIZE / 3 }, (_, index) => index);
const ALL_KINDS = 'all';
const ALL_STATES = 'all';

/**
 * The kind and review-state filters, sort and card size, kept in the URL so a view can be shared
 * and reloaded.
 */
const GalleryOptions = ({
  search,
  onChange,
}: {
  search: GallerySearch;
  onChange: (next: GallerySearch) => void;
}): ReactElement => {
  const copy = useCopy();
  return (
    <>
      <SegmentedControl<AssetKind | typeof ALL_KINDS>
        label={copy.assets.kindFilterLabel}
        isLabelHidden
        name="gallery-kind"
        value={search.kind ?? ALL_KINDS}
        options={[
          { value: ALL_KINDS, label: copy.assets.kindFilter.all },
          {
            value: 'image',
            label: copy.assets.kindFilter.image,
            icon: <Image size={ICON_SIZE.sm} />,
          },
          {
            value: 'model',
            label: copy.assets.kindFilter.model,
            icon: <Box size={ICON_SIZE.sm} />,
          },
        ]}
        onChange={(kind) =>
          onChange(withOption(search, 'kind', kind === ALL_KINDS ? undefined : kind))
        }
      />
      <label className="asset-gallery__sort">
        <ListFilter className="asset-gallery__sort-icon" size={ICON_SIZE.sm} aria-hidden="true" />
        <span className="visually-hidden">{copy.reviews.filterLabel}</span>
        <select
          className="asset-gallery__select"
          value={search.review ?? ALL_STATES}
          onChange={(event) => {
            const review = event.target.value as ReviewState | typeof ALL_STATES;
            onChange(withOption(search, 'review', review === ALL_STATES ? undefined : review));
          }}
        >
          <option value={ALL_STATES}>{copy.reviews.filterAll}</option>
          {REVIEW_STATES.map((state) => (
            <option key={state} value={state}>
              {copy.reviews.state[state]}
            </option>
          ))}
        </select>
      </label>
      <label className="asset-gallery__sort">
        <ArrowDownUp className="asset-gallery__sort-icon" size={ICON_SIZE.sm} aria-hidden="true" />
        <span className="visually-hidden">{copy.assets.sortLabel}</span>
        <select
          className="asset-gallery__select"
          value={search.sort ?? GallerySort.Newest}
          onChange={(event) => {
            const sort = event.target.value as GallerySort;
            onChange(withOption(search, 'sort', sort === GallerySort.Newest ? undefined : sort));
          }}
        >
          {Object.values(GallerySort).map((sort) => (
            <option key={sort} value={sort}>
              {copy.assets.sort[sort]}
            </option>
          ))}
        </select>
      </label>
      <SegmentedControl<CardSize>
        label={copy.assets.sizeLabel}
        isLabelHidden
        isIconOnly
        name="gallery-size"
        value={search.size ?? CardSize.Large}
        options={[
          {
            value: CardSize.Large,
            label: copy.assets.size.large,
            icon: <Grid2x2 size={ICON_SIZE.sm} />,
          },
          {
            value: CardSize.Small,
            label: copy.assets.size.small,
            icon: <Grid3x3 size={ICON_SIZE.sm} />,
          },
        ]}
        onChange={(size) =>
          onChange(withOption(search, 'size', size === CardSize.Large ? undefined : size))
        }
      />
    </>
  );
};

/**
 * The asset grid: a toolbar (title, count, kind filter, sort, card size), its four states and
 * "Load more" pagination. Filter and sort apply to the pages loaded so far (client-side).
 */
export const AssetGallery = (): ReactElement => {
  const copy = useCopy();
  const pages = useAssetPages();
  // The router merges unknown raw params back into the validated ones: parse again to be sure.
  const search = parseGallerySearch(useSearch({ from: '/_app/assets' }));
  const navigate = useNavigate({ from: '/assets' });
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
        : galleryRef.current.querySelectorAll<HTMLElement>('.asset-card__link')[focusAfterLoad];
    target?.focus();
    setFocusAfterLoad(null);
  }, [focusAfterLoad]);
  const refreshOnce = useKeyedThrottle(THUMB_REFRESH_WINDOW_MS);
  const isFetching = pages.isFetching;
  const pendingRefreshRef = useRef(false);
  // One shared refresh re-signs every preview of the list, however many cards fail at once
  // (a storage outage, or lazy cards scrolled into view after the signatures expired). While a
  // page is loading, a refetch would be a no-op, so it waits instead of using up the window.
  const refreshThumbs = useCallback((): void => {
    if (isFetching) {
      pendingRefreshRef.current = true;
      return;
    }
    refreshOnce(ASSET_LIST_QUERY_KEY.join('/'), () => void refetch({ cancelRefetch: false }));
  }, [isFetching, refetch, refreshOnce]);

  useEffect(() => {
    if (isFetching || !pendingRefreshRef.current) return;
    pendingRefreshRef.current = false;
    refreshThumbs();
  }, [isFetching, refreshThumbs]);

  // The view options replace the history entry: back leaves the gallery, not the last filter.
  const setSearch = (next: GallerySearch): void =>
    void navigate({ to: '.', search: next, replace: true });

  const toolbar = (count?: ReactNode, hasOptions = false): ReactElement => (
    <Toolbar
      label={copy.assets.optionsLabel}
      end={hasOptions ? <GalleryOptions search={search} onChange={setSearch} /> : undefined}
    >
      <h1 className="asset-gallery__title">{copy.assets.title}</h1>
      {count === undefined ? null : <span className="asset-gallery__count">{count}</span>}
    </Toolbar>
  );
  const gridClass = `asset-gallery__grid${search.size === CardSize.Small ? ' asset-gallery__grid--small' : ''}`;

  if (pages.isPending) {
    return (
      <div className="asset-gallery" role="status">
        {toolbar()}
        <span className="visually-hidden">{copy.assets.loading}</span>
        <div className={gridClass}>
          {SKELETON_CARDS.map((card) => (
            <Skeleton key={card} shape={SkeletonShape.Card} />
          ))}
        </div>
      </div>
    );
  }
  if (pages.isLoadingError) {
    return (
      <div className="asset-gallery">
        {toolbar()}
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

  const loaded = pages.data.pages.flatMap((page) => page.items);
  if (loaded.length === 0) {
    return (
      <div className="asset-gallery">
        {toolbar()}
        <EmptyState
          title={copy.assets.emptyTitle}
          icon={<Images size={ICON_SIZE.lg} />}
          action={<UploadButton label={copy.uploads.uploadFiles} />}
        >
          {copy.assets.emptyBody}
        </EmptyState>
      </div>
    );
  }
  const assets = visibleAssets(loaded, search);
  const loadMore = async (): Promise<void> => {
    const shownBefore = assets.length;
    const result = await pages.fetchNextPage();
    setFocusAfterLoad(result.isError ? 'error' : shownBefore);
  };
  const filtered = isFiltered(search);
  const count = filtered
    ? copy.assets.countFiltered(assets.length, loaded.length)
    : copy.assets.count(loaded.length, pages.hasNextPage);

  return (
    <div className="asset-gallery" ref={galleryRef}>
      {toolbar(count, true)}
      {assets.length > 0 ? (
        <ul className={gridClass} aria-label={copy.assets.title}>
          {assets.map((asset) => (
            <li key={asset.id} className="asset-gallery__item">
              <AssetCard asset={asset} onThumbError={refreshThumbs} />
            </li>
          ))}
        </ul>
      ) : search.review && !search.kind ? (
        <EmptyState
          title={copy.reviews.filteredEmptyTitle(copy.reviews.state[search.review])}
          icon={<ListFilter size={ICON_SIZE.lg} />}
          action={
            <Button
              variant={ButtonVariant.Secondary}
              onClick={() => setSearch(withOption(search, 'review', undefined))}
            >
              {copy.reviews.showAllStates}
            </Button>
          }
        >
          {copy.reviews.filteredEmptyBody}
        </EmptyState>
      ) : (
        <EmptyState
          title={copy.assets.filteredEmptyTitle[search.kind ?? 'image']}
          icon={
            search.kind === 'model' ? <Box size={ICON_SIZE.lg} /> : <Image size={ICON_SIZE.lg} />
          }
          action={
            <Button
              variant={ButtonVariant.Secondary}
              onClick={() => setSearch(withOption(search, 'kind', undefined))}
            >
              {copy.assets.showAll}
            </Button>
          }
        >
          {copy.assets.filteredEmptyBody}
        </EmptyState>
      )}
      <p className="visually-hidden" aria-live="polite">
        {filtered
          ? copy.assets.shownFiltered(assets.length, loaded.length)
          : copy.assets.shown(assets.length)}
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
