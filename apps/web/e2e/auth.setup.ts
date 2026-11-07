import { spawnSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { expect, test as setup } from '@playwright/test';

import { AUTH_STATE, AUTH_TOKEN, E2E_USER } from './support/user.constant';

const REPO_ROOT = fileURLToPath(new URL('../../..', import.meta.url));
const EMAIL_TAKEN = 3;
const SEEDING = 'e2e seeding';

/** The account exists once per database: create it, or accept that it is already there. */
const ensureUser = (): void => {
  const result = spawnSync(
    'uv',
    [
      'run',
      '--package',
      'kiln-api',
      'python',
      '-m',
      'kiln_api.cli',
      'create-user',
      '--email',
      E2E_USER.email,
      '--name',
      E2E_USER.name,
      '--password-stdin',
    ],
    { cwd: REPO_ROOT, input: `${E2E_USER.password}\n`, encoding: 'utf8' },
  );
  if (result.status !== 0 && result.status !== EMAIL_TAKEN) {
    throw new Error(`create-user failed (${String(result.status)}): ${result.stdout}`);
  }
};

setup('sign in once through the sign-in page', async ({ page }) => {
  ensureUser();

  await page.goto('/assets');
  await expect(page).toHaveURL(/\/sign-in\?redirect=%2Fassets/u);
  await page.getByLabel('Email').fill(E2E_USER.email);
  await page.getByLabel('Password').fill(E2E_USER.password);
  await page.getByRole('button', { name: 'Sign in' }).click();

  await expect(page).toHaveURL(/\/assets$/u);
  await expect(page.getByRole('button', { name: `Account: ${E2E_USER.name}` })).toBeVisible();
  await page.context().storageState({ path: AUTH_STATE });

  // A token for seeding through the API, as the CLI will publish (KILN-17); the previous run's
  // seeding tokens are revoked first so the list stays short.
  const csrf = { 'X-Kiln-Csrf': '1', Origin: new URL(page.url()).origin };
  const listed = (await (await page.request.get('/api/v1/me/tokens')).json()) as {
    items: { id: string; name: string }[];
  };
  for (const old of listed.items.filter((token) => token.name.startsWith(SEEDING))) {
    await page.request.delete(`/api/v1/me/tokens/${old.id}`, { headers: csrf });
  }
  const created = await page.request.post('/api/v1/me/tokens', {
    headers: csrf,
    data: {
      name: `${SEEDING} ${new Date().toISOString()}`,
      scopes: ['read', 'write'],
      expires_in_days: 7,
    },
  });
  expect(created.status()).toBe(201);
  writeFileSync(AUTH_TOKEN, ((await created.json()) as { token: string }).token);
});
