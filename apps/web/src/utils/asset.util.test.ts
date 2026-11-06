import { PROCESSING_POLL_MAX_MS, PROCESSING_POLL_MS } from '@/constants/assets.constant';
import { aDetail, aVersion, signedUrl } from '@/test/fake-api';
import { hasProcessingVersion, keepSignedUrls, processingPollInterval } from '@/utils/asset.util';

const processing = aDetail({
  versions: [aVersion(), aVersion({ id: 'v2', number: 2, status: 'processing' })],
});
const NOW = Date.parse('2026-11-06T12:00:00Z');

describe('hasProcessingVersion', () => {
  it('is true only when a version is processing', () => {
    expect(hasProcessingVersion(undefined)).toBe(false);
    expect(hasProcessingVersion(aDetail())).toBe(false);
    expect(hasProcessingVersion(processing)).toBe(true);
  });
});

describe('processingPollInterval', () => {
  it('polls while processing, for at most five minutes since processing was first seen', () => {
    expect(processingPollInterval(processing, NOW, NOW)).toBe(PROCESSING_POLL_MS);
    expect(processingPollInterval(processing, NOW, NOW + PROCESSING_POLL_MAX_MS - 1)).toBe(
      PROCESSING_POLL_MS,
    );
    expect(processingPollInterval(processing, NOW, NOW + PROCESSING_POLL_MAX_MS)).toBe(false);
  });

  it('does not poll a settled asset or without a start time', () => {
    expect(processingPollInterval(aDetail(), NOW, NOW)).toBe(false);
    expect(processingPollInterval(processing, null, NOW)).toBe(false);
  });
});

describe('keepSignedUrls', () => {
  const signedAt = '20261106T120000Z';
  const old = aDetail({
    thumbnail_url: signedUrl('thumbs/a/v1.webp', signedAt),
    versions: [aVersion({ thumbnail_url: signedUrl('thumbs/a/v1.webp', signedAt) })],
  });
  const resigned = aDetail({
    thumbnail_url: signedUrl('thumbs/a/v1.webp', '20261106T120300Z'),
    versions: [
      aVersion({ thumbnail_url: signedUrl('thumbs/a/v1.webp', '20261106T120300Z') }),
      aVersion({ id: 'v2', number: 2, thumbnail_url: signedUrl('thumbs/a/v2.webp', signedAt) }),
    ],
  });

  it('keeps the old URLs of the same objects while they stay valid', () => {
    const kept = keepSignedUrls(old, resigned, NOW + 3 * 60_000);

    expect(kept.thumbnail_url).toBe(old.thumbnail_url);
    expect(kept.versions[0]?.thumbnail_url).toBe(old.versions[0]?.thumbnail_url);
    expect(kept.versions[1]?.thumbnail_url).toBe(resigned.versions[1]?.thumbnail_url);
  });

  it('takes the new URLs once the old ones are about to expire (15-minute signatures)', () => {
    const kept = keepSignedUrls(old, resigned, NOW + 14 * 60_000);

    expect(kept.thumbnail_url).toBe(resigned.thumbnail_url);
  });

  it('takes the new data for a first load or another asset', () => {
    expect(keepSignedUrls(undefined, resigned, NOW)).toBe(resigned);
    expect(keepSignedUrls(aDetail({ id: 'other' }), resigned, NOW)).toBe(resigned);
  });
});
