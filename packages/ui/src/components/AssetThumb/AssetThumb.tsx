import { type ReactElement, type ReactNode, useState } from 'react';

import { THUMB_SIZE_PX } from '#ui/constants/thumb.constant';

import './AssetThumb.css';

interface AssetThumbProps {
  /** A signed preview URL, or null when there is no ready preview. */
  src: string | null;
  /** Empty when nearby text already names the asset (a card), descriptive otherwise. */
  alt: string;
  /** Shown in the same square when there is no image or it failed to load. */
  placeholder: ReactNode;
  /** Above-the-fold previews (the detail hero) load eagerly. */
  isEager?: boolean;
  /** Called once per failing URL, e.g. to fetch fresh signed URLs. */
  onError?: (src: string) => void;
}

/** A square preview with a fixed intrinsic size, so loading it never shifts the layout. */
export const AssetThumb = ({
  src,
  alt,
  placeholder,
  isEager = false,
  onError,
}: AssetThumbProps): ReactElement => {
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const showImage = src !== null && src !== failedSrc;
  return (
    <div className="asset-thumb">
      {showImage ? (
        <img
          className="asset-thumb__image"
          src={src}
          alt={alt}
          width={THUMB_SIZE_PX}
          height={THUMB_SIZE_PX}
          loading={isEager ? 'eager' : 'lazy'}
          decoding="async"
          onError={() => {
            setFailedSrc(src);
            onError?.(src);
          }}
        />
      ) : (
        <span className="asset-thumb__placeholder">{placeholder}</span>
      )}
    </div>
  );
};
