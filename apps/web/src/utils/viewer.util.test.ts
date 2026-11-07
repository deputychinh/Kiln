import { ViewerError } from '@/enums/viewer-error.enum';
import { aDetail, aVersion } from '@/test/fake-api';
import { parseViewerSearch } from '@/utils/viewer-search.util';
import { isViewable, pickViewable, viewerErrorOf, viewerFailure } from '@/utils/viewer.util';

const model = (number: number, overrides = {}) =>
  aVersion({
    id: `m${String(number)}`,
    number,
    content_type: 'model/gltf-binary',
    file_name: `crate_v${String(number)}.glb`,
    download_url: `http://s3.test/kiln/assets/a/v${String(number)}/m.glb?sig=1`,
    ...overrides,
  });

const crate = aDetail({
  kind: 'model',
  versions: [model(1), model(2), model(3, { status: 'processing', download_url: null })],
});

describe('parseViewerSearch', () => {
  it('keeps a positive whole version number', () => {
    expect(parseViewerSearch({ version: '2' })).toEqual({ version: 2 });
    expect(parseViewerSearch({ version: 7 })).toEqual({ version: 7 });
  });

  it.each(['0', '-1', '1.5', 'abc', '1e3', '01', '1234567890', ''])('drops version=%s', (raw) => {
    expect(parseViewerSearch({ version: raw })).toEqual({});
  });

  it('drops parameters it does not know', () => {
    expect(parseViewerSearch({ mode: 'swipe' })).toEqual({});
  });
});

describe('isViewable', () => {
  it('is a ready model version with a file link', () => {
    expect(isViewable('model', model(1))).toBe(true);
  });

  it.each([
    ['an image', 'image' as const, model(1)],
    ['a processing model', 'model' as const, model(1, { status: 'processing' })],
    ['a failed model', 'model' as const, model(1, { status: 'failed' })],
    ['a ready model without a link', 'model' as const, model(1, { download_url: null })],
    ['an older API without the field', 'model' as const, model(1, { download_url: undefined })],
  ])('is not %s', (_case, kind, version) => {
    expect(isViewable(kind, version)).toBe(false);
  });
});

describe('pickViewable', () => {
  it('shows the version the URL names when it can be viewed', () => {
    expect(pickViewable(crate, 1)).toEqual({ version: crate.versions[0], isCorrected: false });
  });

  it('shows the newest viewable version when the URL names none, without correcting', () => {
    expect(pickViewable(crate, undefined)).toEqual({
      version: crate.versions[1],
      isCorrected: false,
    });
  });

  it('corrects a version that does not exist or is not ready to the newest viewable one', () => {
    expect(pickViewable(crate, 9)).toEqual({ version: crate.versions[1], isCorrected: true });
    expect(pickViewable(crate, 3)).toEqual({ version: crate.versions[1], isCorrected: true });
  });

  it('has nothing to show for an image or a model with no ready version', () => {
    expect(pickViewable(aDetail({ versions: [aVersion()] }), 1)).toBeNull();
    const processing = model(3, { status: 'processing', download_url: null });
    expect(pickViewable(aDetail({ kind: 'model', versions: [processing] }), 3)).toBeNull();
    expect(pickViewable(aDetail({ kind: 'model', versions: [] }), undefined)).toBeNull();
  });
});

describe('viewer failures', () => {
  it('carry their error and are told apart from other errors', () => {
    expect(viewerErrorOf(viewerFailure(ViewerError.TooLarge))).toBe(ViewerError.TooLarge);
    expect(viewerFailure(ViewerError.Unsupported)).toBeInstanceOf(Error);
  });

  it('treat anything else as a failed download', () => {
    expect(viewerErrorOf(new TypeError('Failed to fetch'))).toBe(ViewerError.Download);
    expect(viewerErrorOf('nope')).toBe(ViewerError.Download);
  });
});
