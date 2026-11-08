import { randomUUID } from 'node:crypto';

import { AxeBuilder } from '@axe-core/playwright';
import { expect, type Locator, type Page, test, type TestInfo } from '@playwright/test';

import { seedImageAsset, seedReviewTransition, versionIdsOf } from './support/seed';

// KILN-11: review states, decisions and history against the real API and worker.

const uniqueName = (prefix: string, testInfo: TestInfo): string =>
  `e2e_${prefix}_${testInfo.project.name}_${randomUUID().slice(0, 8)}`;

const seriousViolations = async (page: Page): Promise<string[]> => {
  // From the top of the page: axe counts a target scrolled under the sticky top bar as obscured,
  // so the verdict would otherwise depend on where the last click left the scroll (KILN-11).
  await page.evaluate(() => window.scrollTo(0, 0));
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
    .analyze();
  return results.violations
    .filter((v) => ['serious', 'critical'].includes(v.impact ?? ''))
    .map((v) => `${v.id}: ${v.nodes.map((node) => node.target.join(' ')).join(', ')}`);
};

/** Opens the asset on the Review tab once the worker has made the version ready. */
const openReview = async (page: Page, assetId: string, action = 'Approve'): Promise<Locator> => {
  await expect(async () => {
    await page.goto(`/assets/${assetId}`);
    await page.getByRole('tab', { name: 'Review' }).click();
    await expect(page.getByRole('button', { name: action })).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 60_000 });
  return page.getByRole('form', { name: /^Decide on version / });
};

const header = (page: Page): Locator => page.locator('.asset-detail__header');

/** What `document.activeElement` is, read in the page itself: tag and trimmed text. */
const activeElement = (page: Page): Promise<string> =>
  page.evaluate(() => {
    const active = document.activeElement;
    return active ? `${active.tagName}: ${active.textContent?.trim() ?? ''}` : 'none';
  });
const history = (page: Page): Locator => page.getByRole('region', { name: /^Review history/ });

test('a lead approves with a note, reopens, requests changes, and the gallery follows', async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(120_000);
  const asset = await seedImageAsset(request, uniqueName('review', testInfo));
  const form = await openReview(page, asset.id);
  await expect(header(page)).toContainText('In review');
  await expect(page.getByText('No decisions yet')).toBeVisible();

  await form.getByRole('textbox', { name: 'Note (optional)' }).fill('Edges are clean now.');
  await form.getByRole('button', { name: 'Approve' }).click();

  await expect(header(page)).toContainText('Approved');
  await expect(history(page).getByText(/ approved, from In review to Approved$/)).toBeVisible();
  await expect(history(page).getByText('Edges are clean now.')).toBeVisible();
  await expect(form.getByRole('textbox', { name: 'Note (optional)' })).toHaveValue('');

  await form.getByRole('button', { name: 'Reopen' }).click();
  await expect(header(page)).toContainText('In review');
  await form.getByRole('textbox', { name: 'Note (optional)' }).fill('Swatch is off-brand.');
  await form.getByRole('button', { name: 'Request changes' }).click();
  await expect(header(page)).toContainText('Changes requested');
  await expect(history(page).getByRole('listitem')).toHaveCount(3);

  // Stored, not local state; and the gallery filters by it, kept in the URL.
  await page.goto('/assets?review=changes_requested');
  const card = page.getByRole('link', { name: new RegExp(asset.name) });
  await expect(card).toContainText('Changes requested');
  await page.goto('/assets?review=approved');
  await expect(page.getByRole('link', { name: new RegExp(asset.name) })).toBeHidden();
});

test('a decision made on a state someone else changed is refused and explained', async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(120_000);
  const asset = await seedImageAsset(request, uniqueName('review_conflict', testInfo));
  const form = await openReview(page, asset.id);
  const [versionId = ''] = await versionIdsOf(request, asset.id);
  // Another lead approves from the CLI while this page still shows "In review".
  await seedReviewTransition(request, versionId, {
    action: 'approve',
    expectedState: 'in_review',
    note: 'Approved from the CLI',
  });

  await form.getByRole('textbox', { name: 'Note (optional)' }).fill('Needs a darker rim.');
  await form.getByRole('button', { name: 'Request changes' }).focus();
  await page.keyboard.press('Enter');

  // The refusal takes focus and is no alert, so it is read once; its ring shows (KILN-48).
  const refusal = form.getByText(/^Someone else decided first/);
  await expect(refusal).toContainText('this version is now “Approved”');
  await expect(refusal).toBeFocused();
  await expect(page.getByRole('alert')).toHaveCount(0);
  // Request changes is gone now; focus stays on the message, not on <body> (KILN-48).
  await expect(form.getByRole('button', { name: 'Request changes' })).toBeHidden();
  expect(await activeElement(page)).toMatch(/^P: Someone else decided first/);
  expect(
    await refusal.evaluate(
      (node) => node.matches(':focus-visible') && getComputedStyle(node).outlineStyle === 'solid',
    ),
  ).toBe(true);
  for (const theme of ['dark', 'light'] as const) {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await form.screenshot({
      path: `test-results/screens/kiln-48-refusal-focused-${testInfo.project.name}-${theme}.png`,
    });
  }
  await expect(form.getByRole('button', { name: 'Reopen' })).toBeVisible();
  await expect(form.getByRole('textbox', { name: 'Note (optional)' })).toHaveValue(
    'Needs a darker rim.',
  );
  await expect(history(page).getByText('Approved from the CLI')).toBeVisible();
  await expect(history(page).getByRole('listitem')).toHaveCount(1);
});

test('with the keyboard alone, a version is approved and reopened, focus never lost', async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(120_000);
  // Desktop and Pixel 7 (a phone with a hardware keyboard): KILN-48 asserts focus on both.
  const asset = await seedImageAsset(request, uniqueName('review_keys', testInfo));
  await openReview(page, asset.id);
  await page.getByRole('tab', { name: 'Versions' }).click();

  // Tabs follow the APG: arrows move between them; then Tab enters the panel.
  await page.getByRole('tab', { name: 'Versions' }).focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('tab', { name: 'Review' })).toBeFocused();
  const note = page.getByRole('textbox', { name: 'Note (optional)' });
  for (
    let step = 0;
    step < 4 && !(await note.evaluate((n) => n === document.activeElement));
    step += 1
  ) {
    await page.keyboard.press('Tab');
  }
  await expect(note).toBeFocused();
  await page.keyboard.type('Approved by keyboard.');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('button', { name: 'Approve' })).toBeFocused();
  await page.keyboard.press('Enter');

  await expect(page.getByRole('status').filter({ hasText: /approved$/ })).toHaveText(
    'Version 1 approved',
  );
  await expect(history(page).getByText('Approved by keyboard.')).toBeVisible();
  // Approve unmounted; focus went on purpose to Reopen, never to <body> (KILN-48, WCAG 2.4.3).
  await expect(page.getByRole('button', { name: 'Reopen' })).toBeFocused();
  expect(await activeElement(page)).toBe('BUTTON: Reopen');
  await page.getByRole('form', { name: /^Decide on version / }).screenshot({
    path: `test-results/screens/kiln-48-reopen-focused-${testInfo.project.name}.png`,
  });

  await page.keyboard.press('Enter');
  await expect(page.getByRole('status').filter({ hasText: /review$/ })).toContainText(
    'Version 1 is back in review',
  );
  await expect(page.getByRole('button', { name: 'Approve' })).toBeFocused();
  expect(await activeElement(page)).toBe('BUTTON: Approve');
  await page.getByRole('form', { name: /^Decide on version / }).screenshot({
    path: `test-results/screens/kiln-48-approve-focused-${testInfo.project.name}.png`,
  });
});

test('reopening a version that offers no action focuses the hint, with its ring', async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(120_000);
  // KILN-48 (AC3): a decided version that failed a later re-check (ADR 0011) can only be reopened;
  // after that nothing is offered, so focus goes to the hint that says why. The real API decides;
  // the page is told the version failed (an e2e cannot make a decided version fail).
  const asset = await seedImageAsset(request, uniqueName('review_hint', testInfo));
  await openReview(page, asset.id);
  const [versionId = ''] = await versionIdsOf(request, asset.id);
  await seedReviewTransition(request, versionId, { action: 'approve', expectedState: 'in_review' });
  await page.route(`**/api/v1/assets/${asset.id}`, async (route) => {
    const response = await route.fetch();
    const body = (await response.json()) as {
      versions: { status: string; failure_reason: string | null }[];
    };
    for (const version of body.versions) {
      version.status = 'failed';
      version.failure_reason = 'UNREADABLE_IMAGE';
    }
    await route.fulfill({ response, json: body });
  });
  const form = await openReview(page, asset.id, 'Reopen');

  await form.getByRole('button', { name: 'Reopen' }).focus();
  await page.keyboard.press('Enter');

  const hint = form.getByText(
    'This version can be approved or sent back once it has finished processing.',
  );
  await expect(hint).toBeFocused();
  await expect(page.getByRole('status').filter({ hasText: /review$/ })).toHaveText(
    'Version 1 is back in review',
  );
  for (const theme of ['dark', 'light'] as const) {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    expect(
      await hint.evaluate(
        (node) =>
          node.matches(':focus-visible') &&
          getComputedStyle(node).outlineStyle === 'solid' &&
          parseFloat(getComputedStyle(node).outlineWidth) >= 2,
      ),
    ).toBe(true);
    await form.screenshot({
      path: `test-results/screens/kiln-48-hint-focused-${testInfo.project.name}-${theme}.png`,
    });
  }
});

for (const theme of ['dark', 'light'] as const) {
  test(`the review tab and the badges pass axe and never scroll sideways in the ${theme} theme`, async ({
    page,
    request,
  }, testInfo) => {
    test.setTimeout(120_000);
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    const asset = await seedImageAsset(request, uniqueName(`review_axe_${theme}`, testInfo));
    const form = await openReview(page, asset.id);
    await form.getByRole('textbox', { name: 'Note (optional)' }).fill('Looks right.');
    await form.getByRole('button', { name: 'Approve' }).click();
    await expect(history(page).getByText('Looks right.')).toBeVisible();

    expect(await seriousViolations(page), 'review tab').toEqual([]);
    for (const button of await form.getByRole('button').all()) {
      const box = await button.boundingBox();
      expect(box?.height ?? 0, 'target height').toBeGreaterThanOrEqual(24);
      expect(box?.width ?? 0, 'target width').toBeGreaterThanOrEqual(24);
    }
    const width = page.viewportSize()?.width ?? 0;
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    );

    await page.goto('/assets?sort=attention');
    await expect(page.getByRole('link', { name: new RegExp(asset.name) })).toContainText(
      'Approved',
    );
    expect(await seriousViolations(page), 'gallery').toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    );
  });
}

test('screenshots of the review tab and the gallery badges at 1440, 1280 and 390 px in both themes', async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(240_000);
  test.skip(testInfo.project.name !== 'desktop', 'one set of screenshots is enough');
  const asset = await seedImageAsset(request, uniqueName('review_shots', testInfo));
  const [versionId = ''] = await versionIdsOf(request, asset.id);
  await openReview(page, asset.id);
  await seedReviewTransition(request, versionId, {
    action: 'request_changes',
    expectedState: 'in_review',
    note: 'The swatch reads too warm next to the brand palette; cool it by about 200 K.',
  });
  await seedReviewTransition(request, versionId, {
    action: 'reopen',
    expectedState: 'changes_requested',
  });
  await seedReviewTransition(request, versionId, {
    action: 'approve',
    expectedState: 'in_review',
    note: 'Cooled down — approved.',
  });
  for (const theme of ['dark', 'light'] as const) {
    for (const width of [1440, 1280, 390]) {
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.setViewportSize({ width, height: { 1440: 900, 1280: 800 }[width] ?? 844 });
      await openReview(page, asset.id, 'Reopen');
      if (width > 600) {
        // KILN-11 review: on a wide screen the decision is in view without scrolling the pane.
        await expect(page.getByRole('button', { name: 'Reopen' })).toBeInViewport();
      }
      await expect(history(page).getByText('Cooled down — approved.')).toBeVisible();
      // On wide screens the inspector scrolls on its own: bring the history into its view.
      await history(page).scrollIntoViewIfNeeded();
      await page.screenshot({
        path: `test-results/screens/kiln-11-review-${String(width)}-${theme}.png`,
        fullPage: width < 600,
      });
      await page.goto('/assets?sort=attention');
      await expect(page.getByRole('link', { name: new RegExp(asset.name) })).toBeVisible();
      await page.screenshot({
        path: `test-results/screens/kiln-11-gallery-${String(width)}-${theme}.png`,
      });
    }
  }
});
