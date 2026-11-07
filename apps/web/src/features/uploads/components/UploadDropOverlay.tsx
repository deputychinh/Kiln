import { type DropTarget, DropOverlay, ICON_SIZE } from '@kiln/ui';
import { useQuery } from '@tanstack/react-query';
import { useParams } from '@tanstack/react-router';
import { ImagePlus, Layers } from 'lucide-react';
import type { ReactElement } from 'react';

import { NEW_ASSETS_DROP_TARGET, VERSION_DROP_TARGET } from '@/constants/upload.constant';
import { assetDetailQueryOptions } from '@/features/assets/services/asset-detail.query';
import { useUploadQueue } from '@/features/uploads/context/UploadsContext';
import { useCopy } from '@/hooks/useCopy';

/**
 * Files dragged anywhere over the window can be dropped as new assets, or — while an asset is
 * open — as its next versions. Pointer only: the Upload buttons are the accessible path.
 */
export const UploadDropOverlay = (): ReactElement => {
  const copy = useCopy();
  const uploads = useUploadQueue();
  const { assetId } = useParams({ strict: false });
  // Reads the open asset from the cache the detail filled; never fetches on its own.
  const { data: asset } = useQuery({ ...assetDetailQueryOptions(assetId ?? ''), enabled: false });
  const openAsset = assetId && asset?.id === assetId ? asset : undefined;

  const targets: DropTarget[] = [
    {
      id: NEW_ASSETS_DROP_TARGET,
      label: copy.uploads.overlayAssets,
      hint: copy.uploads.dropHint,
      icon: <ImagePlus size={ICON_SIZE.lg} />,
    },
  ];
  if (openAsset)
    targets.push({
      id: VERSION_DROP_TARGET,
      label: copy.uploads.overlayVersion(openAsset.name),
      hint: copy.uploads.version.hint[openAsset.kind],
      icon: <Layers size={ICON_SIZE.lg} />,
    });

  return (
    <DropOverlay
      title={copy.uploads.overlayTitle}
      targets={targets}
      onDrop={(files, targetId) =>
        targetId === VERSION_DROP_TARGET && openAsset
          ? uploads.add(files, { assetId: openAsset.id, kind: openAsset.kind })
          : uploads.add(files)
      }
    />
  );
};
