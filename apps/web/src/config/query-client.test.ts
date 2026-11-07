import { apiError } from '@/api/client';
import { createQueryClient, shouldRetry } from '@/config/query-client';

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

describe('createQueryClient', () => {
  it('reports a signed-out answer from any query except who-is-signed-in', async () => {
    const onSignedOut = vi.fn();
    const client = createQueryClient(0, onSignedOut);
    const signedOut = (): Promise<never> =>
      Promise.reject(apiError(401, 'Unauthorized', 'UNAUTHENTICATED'));

    await client.fetchQuery({ queryKey: ['me'], queryFn: signedOut }).catch(() => undefined);
    expect(onSignedOut).not.toHaveBeenCalled();
    await client.fetchQuery({ queryKey: ['assets'], queryFn: signedOut }).catch(() => undefined);
    expect(onSignedOut).toHaveBeenCalledTimes(1);
  });

  it('reports a signed-out mutation but not wrong credentials', async () => {
    const onSignedOut = vi.fn();
    const client = createQueryClient(0, onSignedOut);
    const run = (code: string): Promise<unknown> =>
      client
        .getMutationCache()
        .build(client, { mutationFn: () => Promise.reject(apiError(401, 'x', code)) })
        .execute(undefined)
        .catch(() => undefined);

    await run('INVALID_CREDENTIALS');
    expect(onSignedOut).not.toHaveBeenCalled();
    await run('UNAUTHENTICATED');
    expect(onSignedOut).toHaveBeenCalledTimes(1);
  });
});
