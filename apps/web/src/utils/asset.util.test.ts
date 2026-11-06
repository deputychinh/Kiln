import { PROCESSING_POLL_MAX, PROCESSING_POLL_MS } from '@/constants/assets.constant';
import { aDetail, aVersion } from '@/test/fake-api';
import { hasProcessingVersion, processingPollInterval } from '@/utils/asset.util';

const processing = aDetail({
  versions: [aVersion(), aVersion({ id: 'v2', number: 2, status: 'processing' })],
});

describe('hasProcessingVersion', () => {
  it('is true only when a version is processing', () => {
    expect(hasProcessingVersion(undefined)).toBe(false);
    expect(hasProcessingVersion(aDetail())).toBe(false);
    expect(hasProcessingVersion(processing)).toBe(true);
  });
});

describe('processingPollInterval', () => {
  it('polls while processing, up to the maximum number of refreshes', () => {
    expect(processingPollInterval(processing, 1)).toBe(PROCESSING_POLL_MS);
    expect(processingPollInterval(processing, PROCESSING_POLL_MAX)).toBe(PROCESSING_POLL_MS);
    expect(processingPollInterval(processing, PROCESSING_POLL_MAX + 1)).toBe(false);
  });

  it('does not poll a settled asset', () => {
    expect(processingPollInterval(aDetail(), 1)).toBe(false);
  });
});
