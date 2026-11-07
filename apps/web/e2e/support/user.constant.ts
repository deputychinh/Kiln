/**
 * The e2e user: created in the local database by `auth.setup.ts` through `make create-user`'s
 * command. Test-only credentials for a local database; never used anywhere else.
 */
export const E2E_USER = {
  email: 'e2e@kiln.test',
  name: 'E2E Artist',
  password: 'e2e-only-password-for-local-tests',
} as const;

/** Where the setup project leaves the signed-in browser state and a CLI token for seeding. */
export const AUTH_STATE = new URL('../.auth/user.json', import.meta.url).pathname;
export const AUTH_TOKEN = new URL('../.auth/token.txt', import.meta.url).pathname;
