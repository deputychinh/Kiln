import type { AssetVersion } from '@/interfaces/asset.interface';
import type { DraftKey } from '@/interfaces/comment.interface';

/** The version comments open on: the newest ready one (it has a preview), else the newest. */
export const defaultCommentVersion = (versions: AssetVersion[]): AssetVersion | undefined =>
  versions.findLast((version) => version.status === 'ready') ?? versions.at(-1);

/**
 * The idempotency key for a draft: the same content keeps its key, so a retry after a lost answer
 * replays the first result instead of posting twice; changed content gets a new key.
 */
export const draftKey = (current: DraftKey | null, signature: string): DraftKey =>
  current?.signature === signature ? current : { key: crypto.randomUUID(), signature };
