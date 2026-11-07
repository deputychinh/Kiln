import { ICON_SIZE } from '@kiln/ui';
import { Link } from '@tanstack/react-router';
import { Rotate3d } from 'lucide-react';
import type { ReactElement } from 'react';

import { RelativeTime } from '@/components/RelativeTime/RelativeTime';
import { VERSION_STATUS_TONE } from '@/constants/assets.constant';
import { useCopy } from '@/hooks/useCopy';
import type { AssetDetail as AssetDetailData } from '@/interfaces/asset.interface';
import { formatBytes } from '@/utils/format.util';
import { isViewable } from '@/utils/viewer.util';

/** The versions, newest first, as a timeline: a status dot on the line, the facts beside it. */
export const VersionTimeline = ({ asset }: { asset: AssetDetailData }): ReactElement => {
  const copy = useCopy();
  return (
    <ol className="asset-detail__versions">
      {[...asset.versions].reverse().map((version) => {
        const tone = VERSION_STATUS_TONE[version.status];
        return (
          <li key={version.id} className={`asset-detail__version asset-detail__version--${tone}`}>
            <span className="asset-detail__version-head">
              <span className="asset-detail__version-number">
                {copy.assets.versionLabel(version.number)}
              </span>
              <span className="asset-detail__status">{copy.assets.status[version.status]}</span>
              {isViewable(asset.kind, version) ? (
                <Link
                  to="/assets/$assetId/view"
                  params={{ assetId: asset.id }}
                  search={{ version: version.number }}
                  className="asset-detail__view"
                  aria-label={copy.viewer.linkLabel(version.number)}
                >
                  <Rotate3d size={ICON_SIZE.sm} aria-hidden="true" />
                  {copy.viewer.link}
                </Link>
              ) : null}
            </span>
            <span className="asset-detail__file">
              {copy.assets.fileSummary(
                version.file_name,
                formatBytes(version.size_bytes, copy.locale),
              )}
            </span>
            <span className="asset-detail__when">
              <RelativeTime iso={version.created_at} />
            </span>
            {version.failure_reason ? (
              <span className="asset-detail__failure">
                {copy.assets.failure[version.failure_reason]}
              </span>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
};
