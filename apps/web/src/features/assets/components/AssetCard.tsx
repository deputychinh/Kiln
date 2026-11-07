import { AssetThumb, ICON_SIZE, Tooltip } from '@kiln/ui';
import { Link } from '@tanstack/react-router';
import { Box, Image, Rotate3d } from 'lucide-react';
import { memo, type ReactElement } from 'react';

import { RelativeTime } from '@/components/RelativeTime/RelativeTime';
import { useCopy } from '@/hooks/useCopy';
import type { Asset } from '@/interfaces/asset.interface';
import { splitForMiddleEllipsis } from '@/utils/gallery.util';

import './AssetCard.css';

interface AssetCardProps {
  asset: Asset;
  onThumbError: () => void;
}

/**
 * A gallery card: an edge-to-edge 4:3 preview, the name (middle ellipsis, full name on hover),
 * kind and age. The whole card links to the asset (the router marks the open one with
 * `aria-current`); a model with a preview also offers View in 3D on hover and focus.
 */
// Memoised: the gallery re-renders on every upload progress step; the cards need not.
export const AssetCard = memo(({ asset, onThumbError }: AssetCardProps): ReactElement => {
  const copy = useCopy();
  const kind = copy.assets.kind[asset.kind];
  const KindIcon = asset.kind === 'model' ? Box : Image;
  const { head, tail } = splitForMiddleEllipsis(asset.name);
  // A model's preview exists once a version is ready, so the viewer has something to open.
  const canView3d = asset.kind === 'model' && Boolean(asset.thumbnail_url);
  return (
    <div className="asset-card">
      <Link
        to="/assets/$assetId"
        params={{ assetId: asset.id }}
        search={true}
        className="asset-card__link"
        data-asset-id={asset.id}
      >
        <span className="asset-card__preview">
          <AssetThumb
            src={asset.thumbnail_url ?? null}
            alt=""
            placeholder={
              <>
                <KindIcon size={ICON_SIZE.lg} aria-hidden="true" />
                {kind}
              </>
            }
            onError={onThumbError}
          />
          <span className="asset-card__open" aria-hidden="true">
            {copy.assets.open}
          </span>
        </span>
        <span className="asset-card__body">
          <Tooltip content={asset.name} isBlock>
            <span className="asset-card__name">
              <span className="asset-card__name-head">{head}</span>
              {tail ? <span className="asset-card__name-tail">{tail}</span> : null}
            </span>
          </Tooltip>
          <span className="asset-card__meta">
            <span className="asset-card__kind">
              <KindIcon size={ICON_SIZE.sm} aria-hidden="true" />
              {kind}
            </span>
            <RelativeTime iso={asset.updated_at} />
          </span>
        </span>
      </Link>
      {canView3d ? (
        <Link
          to="/assets/$assetId/view"
          params={{ assetId: asset.id }}
          search={{}}
          className="asset-card__action"
          aria-label={copy.assets.viewIn3d(asset.name)}
        >
          <Rotate3d size={ICON_SIZE.sm} aria-hidden="true" />
          {copy.viewer.link}
        </Link>
      ) : null}
    </div>
  );
});
