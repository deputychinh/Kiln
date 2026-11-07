import { AssetThumb, Badge } from '@kiln/ui';
import { type ReactElement, useId } from 'react';

import { RelativeTime } from '@/components/RelativeTime/RelativeTime';
import { VERSION_STATUS_TONE } from '@/constants/assets.constant';
import { useCopy } from '@/hooks/useCopy';
import type { AssetDetail, AssetVersion } from '@/interfaces/asset.interface';
import { formatBytes } from '@/utils/format.util';

/** One version: its preview (or why there is none) and its facts. */
export const VersionPane = ({
  asset,
  version,
  onThumbError,
  hasPreview = true,
}: {
  asset: AssetDetail;
  version: AssetVersion;
  onThumbError: (src: string) => void;
  /** False under the Swipe stage, which already shows the preview; the facts stay. */
  hasPreview?: boolean;
}): ReactElement => {
  const copy = useCopy();
  const captionId = useId();
  return (
    <figure className="compare-page__pane" aria-labelledby={captionId}>
      {!hasPreview ? null : version.thumbnail_url ? (
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
