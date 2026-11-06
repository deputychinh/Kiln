import type { AssetKind, FailureReason, VersionStatus } from '@/interfaces/asset.interface';

export interface Copy {
  /** BCP 47 tag for `Intl` formatting. */
  locale: string;
  app: { name: string; skipToContent: string };
  errors: { unreachable: string; unexpected: string };
  assets: {
    title: string;
    loading: string;
    shown: (count: number) => string;
    emptyTitle: string;
    emptyBody: string;
    loadFailed: string;
    loadMore: string;
    loadingMore: string;
    loadMoreFailed: string;
    retry: string;
    kind: Record<AssetKind, string>;
    status: Record<VersionStatus, string>;
    failure: Record<FailureReason, string>;
    detailLabel: string;
    selectPrompt: string;
    back: string;
    previewAlt: (name: string) => string;
    kindLabel: string;
    created: string;
    updated: string;
    versionsTitle: string;
    versionLabel: (number: number) => string;
    stale: string;
    fileSummary: (name: string, size: string) => string;
    loadingAsset: string;
    loadAssetFailed: string;
    notFoundTitle: string;
    notFoundBody: string;
  };
}
