import { type CSSProperties, type ReactElement, type ReactNode, useState } from 'react';

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

/**
 * A square preview well with a fixed size, so loading never shifts the layout. The image is
 * scaled to fit (never cropped) and its own box carries the checkerboard, so transparent pixels
 * read as transparent while any margin around a non-square image stays a quiet neutral.
 */
export const AssetThumb = ({
  src,
  alt,
  placeholder,
  isEager = false,
  onError,
}: AssetThumbProps): ReactElement => {
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const showImage = src !== null && src !== failedSrc;
  // The drawn image's width / height, known once it loads (square until then).
  const [ratio, setRatio] = useState(1);
  const style = { '--thumb-ratio': String(ratio) } as CSSProperties;
  return (
    <div className="asset-thumb" style={style}>
      {showImage ? (
        <img
          className="asset-thumb__image"
          src={src}
          alt={alt}
          width={THUMB_SIZE_PX}
          height={THUMB_SIZE_PX}
          loading={isEager ? 'eager' : 'lazy'}
          decoding="async"
          onLoad={(event) => {
            const { naturalWidth, naturalHeight } = event.currentTarget;
            if (naturalWidth > 0 && naturalHeight > 0) setRatio(naturalWidth / naturalHeight);
          }}
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
