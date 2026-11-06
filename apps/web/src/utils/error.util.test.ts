import { apiError } from '@/api/client';
import { en } from '@/locales/en';
import { describeError, isNotFound } from '@/utils/error.util';

describe('describeError', () => {
  it('explains an unreachable API in plain words', () => {
    expect(describeError(apiError(0, 'Failed to fetch'), en)).toBe(en.errors.unreachable);
  });

  it('shows the problem title the API sent', () => {
    expect(describeError(apiError(503, 'Storage is unavailable'), en)).toBe(
      'Storage is unavailable',
    );
  });

  it('falls back to a generic sentence', () => {
    expect(describeError(new Error(''), en)).toBe(en.errors.unexpected);
    expect(describeError('boom', en)).toBe(en.errors.unexpected);
  });
});

describe('isNotFound', () => {
  it('is true for 404 and 422 only', () => {
    expect(isNotFound(apiError(404, 'x'))).toBe(true);
    expect(isNotFound(apiError(422, 'x'))).toBe(true);
    expect(isNotFound(apiError(500, 'x'))).toBe(false);
    expect(isNotFound(new Error('x'))).toBe(false);
  });
});
