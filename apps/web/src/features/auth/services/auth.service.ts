import { apiDelete, apiGet, apiPost } from '@/api/client';
import { CURRENT_SESSION_PATH, ME_PATH, SESSIONS_PATH } from '@/constants/auth.constant';
import type { Me } from '@/interfaces/auth.interface';

/** Who is signed in; a 401 `UNAUTHENTICATED` means nobody. */
export const getMe = (signal?: AbortSignal): Promise<Me> => apiGet<Me>(ME_PATH, signal);

/** Opens a session; the API sets the HttpOnly cookie (the page never sees it). */
export const signIn = (email: string, password: string): Promise<Me> =>
  apiPost<Me>(SESSIONS_PATH, { email, password });

/** Ends the session and clears the cookie; safe to repeat. */
export const signOut = (): Promise<void> => apiDelete(CURRENT_SESSION_PATH);
