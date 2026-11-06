import { apiBaseUrl } from '@/config/env';
import type { ApiError } from '@/interfaces/api-error.interface';
import type { ProblemBody } from '@/interfaces/problem.interface';

const PROBLEM_MEDIA_TYPE = 'application/problem+json';

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

/** GET a JSON resource of the Kiln API; any failure becomes an `ApiError` (status 0 = unreachable). */
export const apiGet = async <T>(path: string, signal?: AbortSignal): Promise<T> => {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, {
      headers: { Accept: 'application/json' },
      signal: signal ?? null,
    });
  } catch (cause) {
    if (signal?.aborted) throw cause; // a cancelled query, not a failure
    throw apiError(0, cause instanceof Error ? cause.message : String(cause));
  }
  if (!response.ok) throw await problemOf(response);
  return (await response.json()) as T;
};
