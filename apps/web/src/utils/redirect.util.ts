import { DEFAULT_AFTER_SIGN_IN, SIGN_IN_ROUTE } from '@/constants/auth.constant';

const FIRST_PRINTABLE = 0x20;
const hasControlCharacter = (text: string): boolean =>
  [...text].some((char) => (char.codePointAt(0) ?? 0) < FIRST_PRINTABLE);

/**
 * A return path that can only lead back into this app: it must start with one `/` (no
 * `//host` or `/\host`, which browsers treat as another origin) and is never the sign-in page
 * itself. Anything else is the gallery (open-redirect guard, OWASP Unvalidated Redirects).
 */
export const safeRedirect = (raw: unknown): string => {
  if (typeof raw !== 'string' || !raw.startsWith('/')) return DEFAULT_AFTER_SIGN_IN;
  if (raw.startsWith('//') || raw.startsWith('/\\') || hasControlCharacter(raw)) {
    return DEFAULT_AFTER_SIGN_IN;
  }
  const path = raw.split(/[?#]/u, 1)[0] ?? '';
  return path === SIGN_IN_ROUTE ? DEFAULT_AFTER_SIGN_IN : raw;
};

/** The sign-in route's search: a string `redirect`, and `expired` when a session just ended. */
export const parseSignInSearch = (
  search: Record<string, unknown>,
): { redirect?: string; expired?: true } => ({
  ...(typeof search.redirect === 'string' ? { redirect: search.redirect } : {}),
  ...(search.expired === true || search.expired === 'true' ? { expired: true as const } : {}),
});
