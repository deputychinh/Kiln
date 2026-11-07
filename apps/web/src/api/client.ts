import { apiBaseUrl } from '@/config/env';
import type { ApiError } from '@/interfaces/api-error.interface';
import type { ProblemBody } from '@/interfaces/problem.interface';

const PROBLEM_MEDIA_TYPE = 'application/problem+json';
const HTTP_NO_CONTENT = 204;
/** Every write carries it; a cross-site page cannot add it without a refused preflight. */
const CSRF_HEADERS = { 'X-Kiln-Csrf': '1' } as const;

export const apiError = (status: number, message: string, code: string | null = null): ApiError =>
  Object.assign(new Error(message), { name: 'ApiError' as const, status, code });

export const isApiError = (error: unknown): error is ApiError =>
  error instanceof Error && error.name === 'ApiError';

const problemOf = async (response: Response): Promise<ApiError> => {
  const fallback = apiError(response.status, response.statusText);
  if (!response.headers.get('Content-Type')?.includes(PROBLEM_MEDIA_TYPE)) return fallback;
  try {
    const body = (await response.json()) as ProblemBody;
    return apiError(
      response.status,
      typeof body.title === 'string' ? body.title : response.statusText,
      typeof body.code === 'string' ? body.code : null,
    );
  } catch {
    return fallback; // a broken problem body still reports the status
  }
};

const send = async <T>(
  path: string,
  init: RequestInit & { headers: Record<string, string> },
  signal: AbortSignal | undefined,
): Promise<T> => {
  let response: Response;
  try {
    // Same origin: the browser sends the session cookie; never to another origin.
    response = await fetch(`${apiBaseUrl()}${path}`, {
      ...init,
      credentials: 'same-origin',
      signal: signal ?? null,
    });
  } catch (cause) {
    if (signal?.aborted) throw cause; // a cancelled request, not a failure
    throw apiError(0, cause instanceof Error ? cause.message : String(cause));
  }
  if (!response.ok) throw await problemOf(response);
  if (response.status === HTTP_NO_CONTENT) return undefined as T;
  return (await response.json()) as T;
};

/** GET a JSON resource of the Kiln API; any failure becomes an `ApiError` (status 0 = unreachable). */
export const apiGet = <T>(path: string, signal?: AbortSignal): Promise<T> =>
  send<T>(path, { headers: { Accept: 'application/json' } }, signal);

/** POST JSON to the Kiln API; a key makes a retry replay the first result (KILN-21). */
export const apiPost = <T>(
  path: string,
  body: unknown,
  options: { idempotencyKey?: string; signal?: AbortSignal } = {},
): Promise<T> =>
  send<T>(
    path,
    {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        ...CSRF_HEADERS,
        ...(options.idempotencyKey ? { 'Idempotency-Key': options.idempotencyKey } : {}),
      },
      body: JSON.stringify(body),
    },
    options.signal,
  );

/** DELETE a resource of the Kiln API (204 No Content). */
export const apiDelete = (path: string, signal?: AbortSignal): Promise<void> =>
  send<undefined>(path, { method: 'DELETE', headers: { ...CSRF_HEADERS } }, signal);
