import {
  AssetThumb,
  Badge,
  buttonClassName,
  ButtonVariant,
  ErrorState,
  FilePickerButton,
  ICON_SIZE,
  Skeleton,
  SkeletonShape,
  Tabs,
  Tooltip,
} from '@kiln/ui';
import { Link } from '@tanstack/react-router';
import { ArrowLeft, Box, Columns2, Image, Rotate3d, Upload } from 'lucide-react';
import { type ReactElement, useCallback, useEffect, useRef, useState } from 'react';

import { RelativeTime } from '@/components/RelativeTime/RelativeTime';
import { EXPANDED_MEDIA_QUERY } from '@/constants/layout.constant';
import { VERSION_ACCEPT } from '@/constants/upload.constant';
import { AssetFacts } from '@/features/assets/components/AssetFacts';
import { VersionTimeline } from '@/features/assets/components/VersionTimeline';
import { useAsset } from '@/features/assets/hooks/useAsset';
import { CommentsPanel, visibleThreads } from '@/features/comments/components/CommentsPanel';
import { RegionOverlay } from '@/features/comments/components/RegionOverlay';
import { useAnnotation } from '@/features/comments/hooks/useAnnotation';
import { useThreads } from '@/features/comments/hooks/useComments';
import { UploadList } from '@/features/uploads/components/UploadList';
import { useUploadQueue } from '@/features/uploads/context/UploadsContext';
import { useCopy } from '@/hooks/useCopy';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { useUncoveredFocus } from '@/hooks/useUncoveredFocus';
import type { AssetDetail as AssetDetailData } from '@/interfaces/asset.interface';
import { defaultCommentVersion } from '@/utils/comment.util';
import { withBreaks } from '@/utils/ellipsis.util';
import { describeError, isNotFound } from '@/utils/error.util';
import { pickViewable } from '@/utils/viewer.util';

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
      search={true}
      className={`asset-detail__back${isCompactOnly ? ' asset-detail__back--compact' : ''}`}
    >
      <ArrowLeft size={ICON_SIZE.sm} aria-hidden="true" />
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
  const uploads = useUploadQueue();
  const isExpanded = useMediaQuery(EXPANDED_MEDIA_QUERY);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const uploadRef = useRef<HTMLButtonElement>(null);
  const focusUpload = useCallback(() => uploadRef.current, []);

  // Below the expanded size class the detail replaces the list, so the focused card is gone:
  // move focus to the heading so keyboard and screen-reader users land on the new content.
  useEffect(() => {
    if (!isExpanded) headingRef.current?.focus();
  }, [isExpanded]);

  const kind = copy.assets.kind[asset.kind];
  const KindIcon = asset.kind === 'model' ? Box : Image;
  const target = { assetId: asset.id, kind: asset.kind };
  const newestViewable = pickViewable(asset, undefined)?.version;
  const Heading = isExpanded ? 'h2' : 'h1';

  // Comments (KILN-10): while the tab is open, the preview shows the version being discussed,
  // with its regions over it. The tab and the version are view state, like the open tab was.
  const [tab, setTab] = useState('versions');
  const [chosenVersionId, setChosenVersionId] = useState<string | null>(null);
  const [showResolved, setShowResolved] = useState(false);
  const annotation = useAnnotation();
  const previewRef = useRef<HTMLDivElement>(null);
  const keepFocusUncovered = useUncoveredFocus(previewRef);
  const isCommenting = tab === 'comments';
  const commentVersion =
    asset.versions.find((version) => version.id === chosenVersionId) ??
    defaultCommentVersion(asset.versions);
  const threads = useThreads(isCommenting ? commentVersion?.id : undefined);
  const loadedThreads = threads.data?.pages.flatMap((page) => page.items) ?? [];
  const markedThreads = visibleThreads(loadedThreads, showResolved).shown.filter(
    (thread) => thread.region !== null,
  );
  const previewSrc = isCommenting
    ? (commentVersion?.thumbnail_url ?? null)
    : (asset.thumbnail_url ?? null);
  const canMark = isCommenting && asset.kind === 'image' && Boolean(commentVersion?.thumbnail_url);
  let markHint: string | null = null;
  if (asset.kind === 'model') markHint = copy.comments.modelHint;
  else if (!commentVersion?.thumbnail_url) markHint = copy.comments.noPreviewHint;
  return (
    <article
      className={`asset-detail${isCommenting ? ' asset-detail--commenting' : ''}`}
      aria-labelledby="asset-detail-title"
      onFocus={isCommenting ? keepFocusUncovered : undefined}
    >
      <BackLink isCompactOnly />
      <header className="asset-detail__header">
        {/* The page's main heading when the detail replaces the list; below the list's h1 otherwise. */}
        {/* Two lines at most, wrapping between the parts of the name; the full name on hover. */}
        <Tooltip content={asset.name} isBlock as="div">
          <Heading
            id="asset-detail-title"
            className="asset-detail__title"
            ref={headingRef}
            tabIndex={-1}
          >
            {withBreaks(asset.name)}
          </Heading>
        </Tooltip>
        <span className="asset-detail__kind">
          <Badge icon={<KindIcon size={ICON_SIZE.sm} />}>{kind}</Badge>
          <RelativeTime iso={asset.updated_at} />
        </span>
      </header>
      <div className="asset-detail__actions">
        {newestViewable ? (
          <Link
            to="/assets/$assetId/view"
            params={{ assetId: asset.id }}
            search={{ version: newestViewable.number }}
            className={buttonClassName({ variant: ButtonVariant.Secondary })}
            aria-label={copy.viewer.linkLabel(newestViewable.number)}
          >
            <Rotate3d size={ICON_SIZE.sm} aria-hidden="true" />
            {copy.viewer.link}
          </Link>
        ) : null}
        {asset.versions.length >= 2 ? (
          <Link
            to="/assets/$assetId/compare"
            params={{ assetId: asset.id }}
            className={buttonClassName({ variant: ButtonVariant.Secondary })}
            aria-label={copy.compare.link}
          >
            <Columns2 size={ICON_SIZE.sm} aria-hidden="true" />
            {copy.compare.linkShort}
          </Link>
        ) : null}
        <FilePickerButton
          ref={uploadRef}
          variant={ButtonVariant.Secondary}
          icon={<Upload size={ICON_SIZE.sm} />}
          accessibleName={copy.uploads.version.uploadLabel(asset.name)}
          accept={VERSION_ACCEPT[asset.kind]}
          onFiles={(files) => uploads.add(files, target)}
        >
          {copy.uploads.version.upload}
        </FilePickerButton>
      </div>
      {/* While commenting on a wide screen, the image stays in view above the threads. */}
      <div
        ref={previewRef}
        className={`asset-detail__preview${isCommenting ? ' asset-detail__preview--pinned' : ''}`}
      >
        <AssetThumb
          src={previewSrc}
          alt={
            isCommenting && commentVersion
              ? copy.assets.versionPreviewAlt(asset.name, commentVersion.number)
              : copy.assets.previewAlt(asset.name)
          }
          placeholder={
            <>
              <KindIcon size={ICON_SIZE.lg} aria-hidden="true" />
              {kind}
            </>
          }
          onError={onThumbError}
          isEager
          overlay={
            canMark ? <RegionOverlay threads={markedThreads} annotation={annotation} /> : undefined
          }
        />
      </div>
      {isStale ? (
        <p className="asset-detail__stale" role="status">
          {copy.assets.stale}
        </p>
      ) : null}
      <Tabs
        label={copy.assets.sectionsLabel}
        selectedId={tab}
        onSelect={(id) => {
          setTab(id);
          if (id !== 'comments') annotation.reset();
        }}
        tabs={[
          {
            id: 'versions',
            label: copy.assets.versionsTitle,
            badge: asset.versions.length,
            panel: (
              <div className="asset-detail__panel">
                <UploadList
                  uploads={uploads}
                  target={target}
                  listLabel={copy.uploads.version.listLabel(asset.name)}
                  fallbackFocus={focusUpload}
                />
                <VersionTimeline asset={asset} />
              </div>
            ),
          },
          {
            id: 'comments',
            label: copy.comments.tab,
            panel:
              commentVersion && isCommenting ? (
                <CommentsPanel
                  versions={asset.versions}
                  version={commentVersion}
                  onVersionChange={(versionId) => {
                    setChosenVersionId(versionId);
                    annotation.reset();
                  }}
                  threads={threads}
                  showResolved={showResolved}
                  onShowResolvedChange={setShowResolved}
                  annotation={annotation}
                  canMark={canMark}
                  markHint={markHint}
                />
              ) : null,
          },
          {
            id: 'info',
            label: copy.assets.infoTab,
            panel: <AssetFacts asset={asset} />,
          },
        ]}
      />
    </article>
  );
};

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
