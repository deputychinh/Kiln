import type { ReactElement } from 'react';

import { RelativeTime } from '@/components/RelativeTime/RelativeTime';
import { useCopy } from '@/hooks/useCopy';
import type { AssetDetail } from '@/interfaces/asset.interface';
import { formatBytes, formatDateTime } from '@/utils/format.util';

/** The inspector's Info tab: kind, version count, latest file, created and updated. */
export const AssetFacts = ({ asset }: { asset: AssetDetail }): ReactElement => {
  const copy = useCopy();
  const kind = copy.assets.kind[asset.kind];
  const latest = asset.versions.at(-1);
  return (
    <dl className="asset-detail__facts">
      <dt className="asset-detail__term">{copy.assets.kindLabel}</dt>
      <dd className="asset-detail__value">{kind}</dd>
      <dt className="asset-detail__term">{copy.assets.versionCount}</dt>
      <dd className="asset-detail__value">{asset.versions.length}</dd>
      {latest ? (
        <>
          <dt className="asset-detail__term">{copy.assets.latestFile}</dt>
          <dd className="asset-detail__value asset-detail__value--file">
            {copy.assets.fileSummary(latest.file_name, formatBytes(latest.size_bytes, copy.locale))}
          </dd>
        </>
      ) : null}
      <dt className="asset-detail__term">{copy.assets.created}</dt>
      <dd className="asset-detail__value">{formatDateTime(asset.created_at, copy.locale)}</dd>
      <dt className="asset-detail__term">{copy.assets.updated}</dt>
      <dd className="asset-detail__value">
        <RelativeTime iso={asset.updated_at} />
      </dd>
    </dl>
  );
};
