export const SESSIONS_PATH = '/api/v1/sessions';
export const CURRENT_SESSION_PATH = '/api/v1/sessions/current';
export const ME_PATH = '/api/v1/me';
export const TOKENS_PATH = '/api/v1/me/tokens';
export const ME_QUERY_KEY = ['me'] as const;
export const TOKENS_QUERY_KEY = ['me', 'tokens'] as const;
/** Who is signed in changes rarely; a 401 anywhere clears it at once. */
export const ME_STALE_MS = 5 * 60_000;
/** Where a sign-in goes when no (safe) return path was given. */
export const DEFAULT_AFTER_SIGN_IN = '/assets';
export const SIGN_IN_ROUTE = '/sign-in';
/** The API's codes the web app reacts to (never to message text). */
export const AUTH_CODE = {
  unauthenticated: 'UNAUTHENTICATED',
  invalidCredentials: 'INVALID_CREDENTIALS',
  throttled: 'SIGN_IN_THROTTLED',
} as const;
/** The lifetimes the API offers, in days; the form starts at the middle one. */
export const TOKEN_LIFETIMES = [7, 30, 90, 365] as const;
export const DEFAULT_TOKEN_LIFETIME = 90;
export const TOKEN_NAME_MAX_LENGTH = 80;
/** How long "Copied" stays on the copy button. */
export const COPIED_FEEDBACK_MS = 2_000;
