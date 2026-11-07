import { ViewerError } from '@/enums/viewer-error.enum';
import type { AssetDetail, AssetKind, AssetVersion } from '@/interfaces/asset.interface';
import type { ViewablePick } from '@/interfaces/viewer.interface';

const VIEWER_FAILURE = 'ViewerFailure';
const VIEWER_ERRORS = new Set<string>(Object.values(ViewerError));

/** A ready model version with a link to its file: the worker has checked it. */
export const isViewable = (kind: AssetKind, version: AssetVersion): boolean =>
  kind === 'model' && version.status === 'ready' && Boolean(version.download_url);

/**
 * The version to show: the one the URL names when it can be viewed, else the newest viewable one
 * (correcting a URL that named something else); null when the asset has nothing to view.
 */
export const pickViewable = (
  asset: AssetDetail,
  requested: number | undefined,
): ViewablePick | null => {
  const viewable = asset.versions
    .filter((version) => isViewable(asset.kind, version))
    .sort((a, b) => b.number - a.number);
  const [newest] = viewable;
  if (!newest) return null;
  const named = viewable.find((version) => version.number === requested);
  if (named) return { version: named, isCorrected: false };
  return { version: newest, isCorrected: requested !== undefined };
};

/** An error that says why the viewer cannot show a model. */
export const viewerFailure = (code: ViewerError): Error & { code: ViewerError } =>
  Object.assign(new Error(code), { name: VIEWER_FAILURE, code });

/** The viewer error behind a rejection; anything unexpected while downloading is a download error. */
export const viewerErrorOf = (error: unknown): ViewerError => {
  if (error instanceof Error && error.name === VIEWER_FAILURE && 'code' in error) {
    const { code } = error;
    if (typeof code === 'string' && VIEWER_ERRORS.has(code)) return code as ViewerError;
  }
  return ViewerError.Download;
};
