import { randomUUID } from 'node:crypto';

import { AxeBuilder } from '@axe-core/playwright';
import { expect, type Page, test } from '@playwright/test';

import { API_URL } from './support/api.constant';
import { E2E_USER } from './support/user.constant';

const SIGNED_OUT = { cookies: [], origins: [] };

const seriousViolations = async (page: Page): Promise<string[]> => {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
    .analyze();
  return results.violations
    .filter((v) => ['serious', 'critical'].includes(v.impact ?? ''))
    .map((v) => `${v.id}: ${v.nodes.map((node) => node.target.join(' ')).join(', ')}`);
};

const signIn = async (page: Page, email: string, password: string): Promise<void> => {
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
};

test.describe('signed out', () => {
  test.use({ storageState: SIGNED_OUT });

  test('a deep link goes to sign-in and back after signing in', async ({ page }) => {
    await page.goto('/assets?kind=model&size=small');

    await expect(page).toHaveURL(/\/sign-in\?redirect=/u);
    await expect(page.getByRole('heading', { level: 1, name: 'Sign in to Kiln' })).toBeFocused();
    await expect(page).toHaveTitle('Sign in · Kiln');
    // An unknown account gets the same answer as a wrong password (no user enumeration).
    await signIn(page, `nobody-${randomUUID()}@kiln.test`, 'not the password');
    await expect(page.getByRole('alert')).toHaveText('The email or password is not correct.');
    await expect(page.getByLabel('Password')).toBeFocused();
    await expect(page.getByLabel('Password')).toHaveValue('');

    await signIn(page, E2E_USER.email, E2E_USER.password);

    await expect(page).toHaveURL(/\/assets\?kind=model&size=small$/u);
    await expect(page.getByRole('radio', { name: 'Models' })).toBeChecked();
  });

  test('the API refuses every asset call without a session or token', async ({ request }) => {
    const answers = await Promise.all([
      request.get(`${API_URL}/api/v1/assets`),
      request.post(`${API_URL}/api/v1/assets`, { data: {} }),
      request.get(`${API_URL}/api/v1/me/tokens`),
    ]);

    expect(answers.map((answer) => answer.status())).toEqual([401, 401, 401]);
    expect((await request.get(`${API_URL}/health`)).status()).toBe(200);
  });

  test('signing out ends the session for good', async ({ page, browser }) => {
    await page.goto('/sign-in');
    await signIn(page, E2E_USER.email, E2E_USER.password);
    await expect(page).toHaveURL(/\/assets$/u);
    const cookies = await page.context().cookies();
    const session = cookies.find((cookie) => cookie.name === 'kiln_session');
    expect(session).toMatchObject({ httpOnly: true, sameSite: 'Lax', path: '/' });

    await page.getByRole('button', { name: `Account: ${E2E_USER.name}` }).click();
    await page.getByRole('button', { name: 'Sign out' }).click();

    await expect(page).toHaveURL(/\/sign-in$/u);
    // The old cookie, replayed elsewhere, no longer opens anything.
    const replay = await browser.newContext({ storageState: { cookies, origins: [] } });
    const stolen = await replay.request.get('/api/v1/me');
    expect(stolen.status()).toBe(401);
    await replay.close();
  });
});

test('a personal access token is shown once, works with Bearer and stops when revoked', async ({
  page,
  request,
}, testInfo) => {
  const name = `e2e ${testInfo.project.name} ${randomUUID().slice(0, 6)}`;
  await page.goto('/assets');
  await page.getByRole('button', { name: `Account: ${E2E_USER.name}` }).click();
  await page.getByRole('link', { name: 'Settings' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Settings' })).toBeFocused();

  await page.getByRole('textbox', { name: 'Name' }).fill(name);
  await page.getByRole('radio', { name: 'Read only' }).check();
  await page.getByRole('button', { name: 'Create token' }).click();

  await expect(page.getByRole('heading', { name: `Token “${name}” created` })).toBeFocused();
  const secret = await page.getByRole('textbox', { name: 'Your new token' }).inputValue();
  expect(secret).toMatch(/^kiln_pat_[\w-]{43}$/u);
  const bearer = { Authorization: `Bearer ${secret}` };
  expect((await request.get(`${API_URL}/api/v1/assets`, { headers: bearer })).status()).toBe(200);
  // Read only: a write is refused (403, not a silent success).
  const write = await request.post(`${API_URL}/api/v1/assets`, {
    headers: bearer,
    data: { name: 'x', file_name: 'x.png', content_type: 'image/png', size_bytes: 1 },
  });
  expect(write.status()).toBe(403);

  await page.getByRole('button', { name: 'Done' }).click();
  await expect(page.getByText(secret)).toHaveCount(0);
  await page.getByRole('button', { name: `Revoke ${name}` }).click();
  await page.getByRole('button', { name: 'Revoke token' }).click();
  await expect(page.getByText(`Token “${name}” revoked.`)).toBeAttached();

  expect((await request.get(`${API_URL}/api/v1/assets`, { headers: bearer })).status()).toBe(401);
});

for (const theme of ['dark', 'light'] as const) {
  test.describe(`${theme} theme`, () => {
    test.use({ colorScheme: theme, reducedMotion: 'reduce' });

    test(`settings and the user menu pass axe in the ${theme} theme`, async ({ page }) => {
      await page.goto('/settings');
      await expect(page.getByRole('heading', { level: 1, name: 'Settings' })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Create token' })).toBeVisible();
      expect(await seriousViolations(page), 'settings').toEqual([]);
      await page.getByRole('button', { name: `Account: ${E2E_USER.name}` }).click();
      expect(await seriousViolations(page), 'user menu').toEqual([]);
      await page.keyboard.press('Escape');
      await expect(page.getByRole('button', { name: 'Sign out' })).toBeHidden();
    });

    test.describe('signed out', () => {
      test.use({ storageState: SIGNED_OUT });

      test(`sign-in passes axe with its errors in the ${theme} theme`, async ({ page }) => {
        await page.goto('/sign-in');
        await page.getByRole('button', { name: 'Sign in' }).click(); // both field errors
        await expect(page.getByLabel('Email')).toBeFocused();

        expect(await seriousViolations(page), 'sign-in with errors').toEqual([]);
        const width = page.viewportSize()?.width ?? 0;
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
          width,
        );
      });
    });
  });
}

test('screenshots of sign-in and settings at 1440 and 390 px in both themes', async ({
  page,
  browser,
}, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'one set of screenshots is enough');
  for (const theme of ['dark', 'light'] as const) {
    for (const width of [1440, 390]) {
      const viewport = { width, height: width > 600 ? 900 : 844 };
      const signedOut = await browser.newContext({
        storageState: SIGNED_OUT,
        colorScheme: theme,
        viewport,
      });
      const signInPage = await signedOut.newPage();
      await signInPage.goto('/sign-in');
      await expect(signInPage.getByRole('button', { name: 'Sign in' })).toBeVisible();
      await signInPage.screenshot({
        path: `test-results/screens/kiln-12-sign-in-${String(width)}-${theme}.png`,
      });
      await signedOut.close();

      await page.emulateMedia({ colorScheme: theme });
      await page.setViewportSize(viewport);
      await page.goto('/settings');
      await expect(page.getByRole('button', { name: 'Create token' })).toBeVisible();
      await expect(page.locator('.token-list, .empty-state').first()).toBeVisible();
      await page.screenshot({
        path: `test-results/screens/kiln-12-settings-${String(width)}-${theme}.png`,
        fullPage: true,
      });
    }
  }
});
