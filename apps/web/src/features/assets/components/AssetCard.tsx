import { AssetThumb, Badge } from '@kiln/ui';
import { Link } from '@tanstack/react-router';
import { memo, type ReactElement } from 'react';

import { RelativeTime } from '@/components/RelativeTime/RelativeTime';
import { useCopy } from '@/hooks/useCopy';
import type { Asset } from '@/interfaces/asset.interface';

import './AssetCard.css';

interface AssetCardProps {
  asset: Asset;
  onThumbError: () => void;
}

/** A gallery tile linking to the asset; the router marks the open one with `aria-current`. */
// Memoised: the gallery re-renders on every upload progress step; the cards need not.
export const AssetCard = memo(({ asset, onThumbError }: AssetCardProps): ReactElement => {
  const copy = useCopy();
  const kind = copy.assets.kind[asset.kind];
  return (
    <Link
      to="/assets/$assetId"
      params={{ assetId: asset.id }}
      className="asset-card"
      data-asset-id={asset.id}
    >
      <AssetThumb
        src={asset.thumbnail_url ?? null}
        alt=""
        placeholder={kind}
        onError={onThumbError}
      />
      <span className="asset-card__name" title={asset.name}>
        {asset.name}
      </span>
      <span className="asset-card__meta">
        <Badge>{kind}</Badge>
        <RelativeTime iso={asset.updated_at} />
      </span>
    </Link>
  );
});
