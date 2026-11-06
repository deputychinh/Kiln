import { keepSignedUrl, signedUrlExpiresAt } from '@/utils/signed-url.util';

const URL_A =
  'http://s3.test/b/k.webp?X-Amz-Date=20261106T120000Z&X-Amz-Expires=900&X-Amz-Signature=a';
const URL_B =
  'http://s3.test/b/k.webp?X-Amz-Date=20261106T120500Z&X-Amz-Expires=900&X-Amz-Signature=b';
const OTHER = 'http://s3.test/b/other.webp?X-Amz-Date=20261106T120500Z&X-Amz-Expires=900';
const T0 = Date.parse('2026-11-06T12:00:00Z');

describe('signedUrlExpiresAt', () => {
  it('reads the SigV4 date and lifetime', () => {
    expect(signedUrlExpiresAt(URL_A)).toBe(T0 + 900_000);
  });

  it.each([
    'http://s3.test/k.webp',
    'http://s3.test/k.webp?X-Amz-Date=bad&X-Amz-Expires=900',
    'http://s3.test/k.webp?X-Amz-Date=20261106T120000Z&X-Amz-Expires=0',
    'http://s3.test/k.webp?X-Amz-Date=20261106T120000Z&X-Amz-Expires=x',
    '/relative/k.webp?X-Amz-Date=20261106T120000Z&X-Amz-Expires=900',
  ])('is null when it cannot tell: %s', (url) => {
    expect(signedUrlExpiresAt(url)).toBeNull();
  });
});

describe('keepSignedUrl', () => {
  it('keeps the previous URL of the same object while it has enough time left', () => {
    expect(
      keepSignedUrl({ previous: URL_A, next: URL_B, minRemainingMs: 120_000, now: T0 + 780_000 }),
    ).toBe(URL_A);
    expect(
      keepSignedUrl({ previous: URL_A, next: URL_B, minRemainingMs: 120_000, now: T0 + 780_001 }),
    ).toBe(URL_B);
  });

  it('takes the next URL for another object, a missing one, or an unknown expiry', () => {
    expect(keepSignedUrl({ previous: URL_A, next: OTHER, minRemainingMs: 120_000, now: T0 })).toBe(
      OTHER,
    );
    expect(keepSignedUrl({ previous: null, next: URL_B, minRemainingMs: 120_000, now: T0 })).toBe(
      URL_B,
    );
    expect(
      keepSignedUrl({ previous: URL_A, next: null, minRemainingMs: 120_000, now: T0 }),
    ).toBeNull();
    expect(
      keepSignedUrl({ previous: URL_A, next: undefined, minRemainingMs: 120_000, now: T0 }),
    ).toBeNull();
    expect(
      keepSignedUrl({
        previous: 'http://s3.test/b/k.webp?sig=1',
        next: URL_B,
        minRemainingMs: 120_000,
        now: T0,
      }),
    ).toBe(URL_B);
  });
});
