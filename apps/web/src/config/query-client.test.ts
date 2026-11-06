import { apiError } from '@/api/client';
import { shouldRetry } from '@/config/query-client';

describe('shouldRetry', () => {
  it.each([400, 404, 422, 499])('never retries a %i answer', (status) => {
    expect(shouldRetry(0, apiError(status, 'x'))).toBe(false);
  });

  it.each([0, 500, 503])('retries status %i twice, then stops', (status) => {
    expect(shouldRetry(0, apiError(status, 'x'))).toBe(true);
    expect(shouldRetry(1, apiError(status, 'x'))).toBe(true);
    expect(shouldRetry(2, apiError(status, 'x'))).toBe(false);
  });

  it('retries an unknown error like a network failure', () => {
    expect(shouldRetry(0, new Error('boom'))).toBe(true);
  });
});
