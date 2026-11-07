import type { UploadRejection } from '@/enums/upload-rejection.enum';
import type { UploadStatus } from '@/enums/upload-status.enum';
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
  uploads: {
    panelLabel: string;
    dropLabel: string;
    dropHint: string;
    choose: string;
    listLabel: string;
    summary: (finished: number, total: number, failed: number) => string;
    cancelledAfterCreate: string;
    status: Record<UploadStatus, string>;
    progress: (percent: number) => string;
    progressLabel: (fileName: string) => string;
    cancelShort: string;
    retryShort: string;
    removeShort: string;
    cancel: (fileName: string) => string;
    retry: (fileName: string) => string;
    remove: (fileName: string) => string;
    announce: (fileName: string, status: string) => string;
    rejected: Record<UploadRejection, string>;
    storageRejected: string;
    busy: string;
    stalled: string;
    refused: { name: string; size: string; other: string };
    /** The version zone in an asset's detail. */
    version: {
      title: string;
      dropLabel: (assetName: string) => string;
      hint: Record<AssetKind, string>;
      choose: string;
      listLabel: (assetName: string) => string;
    };
  };
}
