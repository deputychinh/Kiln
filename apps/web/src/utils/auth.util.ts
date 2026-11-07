import { isApiError } from '@/api/client';
import { AUTH_CODE } from '@/constants/auth.constant';
import { TokenAccess } from '@/enums/token-access.enum';
import type { AccessToken, TokenScope } from '@/interfaces/auth.interface';

const HTTP_UNAUTHORIZED = 401;

/** The session (or token) is missing, expired or revoked: the person must sign in again. */
export const isSignedOut = (error: unknown): boolean =>
  isApiError(error) &&
  error.status === HTTP_UNAUTHORIZED &&
  error.code === AUTH_CODE.unauthenticated;

/** Up to two letters for an avatar: "Ada Artist" → "AA", "ada" → "A". */
export const initialsOf = (name: string): string =>
  name
    .trim()
    .split(/\s+/u)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => [...word][0]?.toUpperCase() ?? '')
    .join('');

/** The scopes the API expects for an access choice. */
export const scopesFor = (access: TokenAccess): TokenScope[] =>
  access === TokenAccess.ReadWrite ? ['read', 'write'] : ['read'];

/** True once a token is past its expiry (it is listed until revoked, but no longer works). */
export const isExpired = (token: Pick<AccessToken, 'expires_at'>, now = Date.now()): boolean =>
  Date.parse(token.expires_at) <= now;
