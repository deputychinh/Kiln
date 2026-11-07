import { EmptyState, ErrorState, ICON_SIZE, Skeleton, SkeletonShape } from '@kiln/ui';
import { Link, useNavigate, useSearch } from '@tanstack/react-router';
import { ArrowLeft } from 'lucide-react';
import { type ReactElement, useEffect, useRef } from 'react';

import { RelativeTime } from '@/components/RelativeTime/RelativeTime';
import { VIEWER_ROUTE_ID } from '@/constants/viewer.constant';
import { useAsset } from '@/features/assets/hooks/useAsset';
import { ModelViewer } from '@/features/viewer/components/ModelViewer';
import { useCopy } from '@/hooks/useCopy';
import type { AssetDetail, AssetVersion } from '@/interfaces/asset.interface';
import { describeError, isNotFound } from '@/utils/error.util';
import { formatBytes } from '@/utils/format.util';
import { pickViewable } from '@/utils/viewer.util';

import './ViewerPage.css';

interface ViewerPageProps {
  assetId: string;
}

const BackLink = ({ assetId }: { assetId: string }): ReactElement => {
  const copy = useCopy();
  return (
    <Link to="/assets/$assetId" params={{ assetId }} className="viewer-page__back">
      <ArrowLeft size={ICON_SIZE.sm} aria-hidden="true" />
      {copy.viewer.back}
    </Link>
  );
};

const ViewerBody = ({
  asset,
  version,
  onPreviewError,
  onRetry,
}: {
  asset: AssetDetail;
  version: AssetVersion & { download_url: string };
  onPreviewError: (src: string) => void;
  onRetry: () => Promise<unknown>;
}): ReactElement => {
  const copy = useCopy();
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => headingRef.current?.focus(), []);

  return (
    <article className="viewer-page" aria-labelledby="viewer-title">
      <header className="viewer-page__header">
        <BackLink assetId={asset.id} />
        <h1 id="viewer-title" className="viewer-page__title" ref={headingRef} tabIndex={-1}>
          {copy.viewer.title(asset.name, version.number)}
        </h1>
      </header>
      <ModelViewer
        fileUrl={version.download_url}
        sizeBytes={version.size_bytes}
        versionNumber={version.number}
        previewUrl={version.thumbnail_url ?? null}
        onPreviewError={onPreviewError}
        onRetry={onRetry}
      >
        <dl className="viewer-page__facts">
          <dt className="viewer-page__term">{copy.assets.kindLabel}</dt>
          <dd className="viewer-page__value">{copy.assets.kind[asset.kind]}</dd>
          <dt className="viewer-page__term">{copy.assets.versionLabel(version.number)}</dt>
          <dd className="viewer-page__value viewer-page__file">
            {copy.assets.fileSummary(
              version.file_name,
              formatBytes(version.size_bytes, copy.locale),
            )}
          </dd>
          <dt className="viewer-page__term">{copy.assets.updated}</dt>
          <dd className="viewer-page__value">
            <RelativeTime iso={version.updated_at} />
          </dd>
        </dl>
      </ModelViewer>
    </article>
  );
};

/** A model version in 3D, full width; the version lives in the URL (`?version=`). */
export const ViewerPage = ({ assetId }: ViewerPageProps): ReactElement => {
  const copy = useCopy();
  const search = useSearch({ from: VIEWER_ROUTE_ID });
  const navigate = useNavigate({ from: '/assets/$assetId/view' });
  const { query: asset, reportBrokenThumb } = useAsset(assetId);
  const { refetch } = asset;
  const pick = asset.data ? pickViewable(asset.data, search.version) : null;

  // A URL naming a version that cannot be viewed is rewritten in place, never added to history.
  const correctedTo = pick?.isCorrected ? pick.version.number : undefined;
  useEffect(() => {
    if (correctedTo === undefined) return;
    void navigate({ search: { version: correctedTo }, replace: true });
  }, [correctedTo, navigate]);

  if (asset.isPending) {
    return (
      <div className="viewer-page" role="status">
        <span className="visually-hidden">{copy.viewer.loading}</span>
        <Skeleton shape={SkeletonShape.Tile} />
        <Skeleton />
      </div>
    );
  }
  if (asset.isLoadingError) {
    return (
      <div className="viewer-page">
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
  const { version } = pick ?? {};
  if (!version?.download_url) {
    return (
      <div className="viewer-page">
        <EmptyState title={copy.viewer.noneTitle} action={<BackLink assetId={assetId} />}>
          {asset.data.kind === 'model' ? copy.viewer.noneModel : copy.viewer.noneImage}
        </EmptyState>
      </div>
    );
  }
  return (
    <ViewerBody
      asset={asset.data}
      version={{ ...version, download_url: version.download_url }}
      onPreviewError={reportBrokenThumb}
      onRetry={refetch}
    />
  );
};
