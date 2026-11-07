import type { components } from '@/api/kiln.schema';

type Schemas = components['schemas'];

export type Me = Schemas['MeOut'];
export type AccessToken = Schemas['TokenOut'];
export type CreatedToken = Schemas['CreatedTokenOut'];
export type TokenList = Schemas['TokenListOut'];
export type CreateTokenRequest = Schemas['CreateTokenRequest'];
export type TokenScope = Schemas['Scope'];
export type TokenLifetime = CreateTokenRequest['expires_in_days'];

/** What is wrong with the sign-in form's fields before it is sent. */
export interface SignInFieldErrors {
  email?: string;
  password?: string;
}
