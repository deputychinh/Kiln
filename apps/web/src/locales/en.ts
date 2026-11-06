import type { Copy } from '@/interfaces/copy.interface';

export const en: Copy = {
  locale: 'en',
  app: {
    name: 'Kiln',
    skipToContent: 'Skip to content',
  },
  errors: {
    unreachable: 'Kiln cannot reach its server. Check your connection, then try again.',
    unexpected: 'Something went wrong.',
  },
  assets: {
    title: 'Assets',
    loading: 'Loading assets…',
    shown: (count) => `Showing ${String(count)} ${count === 1 ? 'asset' : 'assets'}`,
    emptyTitle: 'No assets yet',
    emptyBody:
      'Publish your first image or glTF model through the Kiln API. It appears here with a preview once it is processed.',
    loadFailed: 'Could not load assets',
    loadMore: 'Load more',
    loadingMore: 'Loading more…',
    loadMoreFailed: 'Could not load more assets',
    retry: 'Try again',
    kind: { image: 'Image', model: 'Model' },
    status: {
      pending_upload: 'Waiting for upload',
      processing: 'Processing',
      ready: 'Ready',
      failed: 'Failed',
    },
    failure: {
      UPLOAD_CHANGED: 'The file changed after it was uploaded. Upload it again.',
      UNREADABLE_IMAGE: 'This is not a readable PNG, JPEG or WebP image.',
      IMAGE_TOO_LARGE: 'The image has too many pixels to preview.',
      PROCESSING_GAVE_UP: 'Processing failed several times. Upload the file again later.',
    },
    detailLabel: 'Asset details',
    selectPrompt: 'Select an asset to see its versions.',
    back: 'All assets',
    previewAlt: (name) => `Preview of ${name}`,
    kindLabel: 'Kind',
    created: 'Created',
    updated: 'Updated',
    versionsTitle: 'Versions',
    versionLabel: (number) => `Version ${String(number)}`,
    stale: 'Could not refresh, so this may be out of date.',
    fileSummary: (name, size) => `${name} · ${size}`,
    loadingAsset: 'Loading asset…',
    loadAssetFailed: 'Could not load this asset',
    notFoundTitle: 'Asset not found',
    notFoundBody: 'It may have been removed, or the link is wrong.',
  },
};
