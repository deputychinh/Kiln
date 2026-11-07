import { apiDelete, apiGet, apiPost } from '@/api/client';
import { TOKENS_PATH } from '@/constants/auth.constant';
import type { CreatedToken, CreateTokenRequest, TokenList } from '@/interfaces/auth.interface';

/** Your tokens that are not revoked, newest first; never their secrets. */
export const listTokens = (signal?: AbortSignal): Promise<TokenList> =>
  apiGet<TokenList>(TOKENS_PATH, signal);

/** A new token; its secret is in this answer only. */
export const createToken = (request: CreateTokenRequest): Promise<CreatedToken> =>
  apiPost<CreatedToken>(TOKENS_PATH, request);

/** Revokes a token at once. */
export const revokeToken = (id: string): Promise<void> =>
  apiDelete(`${TOKENS_PATH}/${encodeURIComponent(id)}`);
