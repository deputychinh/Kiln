import { apiDelete, apiError, apiGet, apiPost, isApiError } from '@/api/client';
import { json, problem } from '@/test/fake-api';

describe('apiGet', () => {
  afterEach(() => vi.restoreAllMocks());

  it('returns the JSON body from the configured API base URL', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ ok: true }));

    await expect(apiGet('/api/v1/assets')).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith('http://api.test/api/v1/assets', {
      headers: { Accept: 'application/json' },
      credentials: 'same-origin',
      signal: null,
    });
  });

  it('turns problem details into an ApiError with the status, title and code', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      problem(503, 'Storage is unavailable', 'STORAGE_UNAVAILABLE'),
    );

    const error: unknown = await apiGet('/x').catch((caught: unknown) => caught);

    expect(isApiError(error)).toBe(true);
    expect(error).toMatchObject({
      status: 503,
      message: 'Storage is unavailable',
      code: 'STORAGE_UNAVAILABLE',
    });
  });

  it('falls back to the status text for a non-problem error or a broken problem body', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('<html>', { status: 502, statusText: 'Bad Gateway' }))
      .mockResolvedValueOnce(
        new Response('{', {
          status: 500,
          statusText: 'Internal Server Error',
          headers: { 'Content-Type': 'application/problem+json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ title: 42, code: null }), {
          status: 400,
          statusText: 'Bad Request',
          headers: { 'Content-Type': 'application/problem+json' },
        }),
      );

    await expect(apiGet('/x')).rejects.toMatchObject({ status: 502, message: 'Bad Gateway' });
    await expect(apiGet('/x')).rejects.toMatchObject({
      status: 500,
      message: 'Internal Server Error',
      code: null,
    });
    await expect(apiGet('/x')).rejects.toMatchObject({ status: 400, message: 'Bad Request' });
  });

  it('reports an unreachable API as status 0', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));

    await expect(apiGet('/x')).rejects.toMatchObject({ name: 'ApiError', status: 0 });
  });

  it('rethrows a cancellation as is, so it is not shown as a failure', async () => {
    const controller = new AbortController();
    const abort = new DOMException('Aborted', 'AbortError');
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => {
      controller.abort();
      return Promise.reject(abort);
    });

    await expect(apiGet('/x', controller.signal)).rejects.toBe(abort);
  });
});

describe('isApiError', () => {
  it('accepts only errors built by apiError', () => {
    expect(isApiError(apiError(404, 'Not found'))).toBe(true);
    expect(isApiError(new Error('boom'))).toBe(false);
    expect(isApiError({ name: 'ApiError' })).toBe(false);
  });
});

describe('apiPost', () => {
  afterEach(() => vi.restoreAllMocks());

  it('sends a JSON body with the idempotency key and returns the JSON reply', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ id: 'a' }, 201));

    await expect(
      apiPost('/api/v1/assets', { name: 'rock' }, { idempotencyKey: 'key-1' }),
    ).resolves.toEqual({ id: 'a' });
    expect(fetchMock).toHaveBeenCalledWith('http://api.test/api/v1/assets', {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-Kiln-Csrf': '1',
        'Idempotency-Key': 'key-1',
      },
      body: '{"name":"rock"}',
      credentials: 'same-origin',
      signal: null,
    });
  });

  it('sends no idempotency header without a key', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({}));

    await apiPost('/x', {});

    expect(fetchMock.mock.calls[0]?.[1]?.headers).not.toHaveProperty('Idempotency-Key');
  });

  it('maps problems and unreachable servers like apiGet', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(problem(415, 'Unsupported type', 'UNSUPPORTED_MEDIA_TYPE'))
      .mockRejectedValueOnce(new TypeError('Failed to fetch'));

    await expect(apiPost('/x', {})).rejects.toMatchObject({
      status: 415,
      code: 'UNSUPPORTED_MEDIA_TYPE',
    });
    await expect(apiPost('/x', {})).rejects.toMatchObject({ status: 0 });
  });

  it('rethrows an abort instead of calling it unreachable', async () => {
    const controller = new AbortController();
    controller.abort();
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new DOMException('Aborted', 'AbortError'));

    await expect(apiPost('/x', {}, { signal: controller.signal })).rejects.toMatchObject({
      name: 'AbortError',
    });
  });
});

describe('apiDelete', () => {
  afterEach(() => vi.restoreAllMocks());

  it('sends the CSRF header with the cookie and resolves on 204 without a body', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(null, { status: 204 }));

    await expect(apiDelete('/api/v1/me/tokens/t1')).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledWith('http://api.test/api/v1/me/tokens/t1', {
      method: 'DELETE',
      headers: { 'X-Kiln-Csrf': '1' },
      credentials: 'same-origin',
      signal: null,
    });
  });

  it('maps a problem to an ApiError like the other verbs', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      problem(404, 'Not Found', 'ACCESS_TOKEN_NOT_FOUND'),
    );

    await expect(apiDelete('/x')).rejects.toMatchObject({
      status: 404,
      code: 'ACCESS_TOKEN_NOT_FOUND',
    });
  });
});
