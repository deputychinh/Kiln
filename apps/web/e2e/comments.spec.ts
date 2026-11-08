import { randomUUID } from 'node:crypto';

import { AxeBuilder } from '@axe-core/playwright';
import { expect, type Locator, type Page, test, type TestInfo } from '@playwright/test';

import { seedImageAsset, seedReply, seedResolved, seedThread, versionIdsOf } from './support/seed';

// KILN-10: region annotations and comment threads on an image version, against the real API.

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

/** Opens the asset once the worker has made its preview, on the Comments tab, preview loaded. */
const openComments = async (page: Page, assetId: string): Promise<Locator> => {
  await expect(async () => {
    await page.goto(`/assets/${assetId}`);
    await page.getByRole('tab', { name: 'Comments' }).click();
    await expect(page.locator('.region-overlay')).toBeAttached({ timeout: 2_000 });
  }).toPass({ timeout: 60_000 });
  return page.locator('.region-overlay');
};

/** Drags across the image's box from one fraction of it to another. */
const drag = async (
  page: Page,
  overlay: Locator,
  [fromX, fromY, toX, toY]: [number, number, number, number],
): Promise<void> => {
  await overlay.scrollIntoViewIfNeeded();
  const box = await overlay.boundingBox();
  if (!box) throw new Error('the overlay has no box');
  await page.mouse.move(box.x + box.width * fromX, box.y + box.height * fromY);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * toX, box.y + box.height * toY, { steps: 5 });
  await page.mouse.up();
};

test('a reviewer drags a region, comments on it, gets a reply and resolves the thread', async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(120_000);
  const asset = await seedImageAsset(request, uniqueName('comments', testInfo));
  const overlay = await openComments(page, asset.id);
  await expect(page.getByRole('heading', { name: 'No comments yet' })).toBeVisible();

  await page.getByRole('button', { name: 'Mark region' }).click();
  await drag(page, overlay, [0.2, 0.25, 0.6, 0.75]);
  await expect(page.getByText('Rectangle marked on the image')).toBeVisible();
  await page.getByRole('textbox', { name: 'New comment' }).fill('The swatch edge is too hard.');
  await page.getByRole('button', { name: 'Post comment' }).click();

  const mark = page.getByRole('button', { name: 'Region 1: The swatch edge is too hard.' });
  await expect(mark).toBeVisible();
  // The rectangle sits where it was drawn, relative to the image (normalised, ±1 %).
  const box = await overlay.boundingBox();
  const markBox = await overlay.locator('.region-overlay__rect').boundingBox();
  if (!box || !markBox) throw new Error('no boxes');
  expect((markBox.x - box.x) / box.width).toBeCloseTo(0.2, 1);
  expect((markBox.y - box.y) / box.height).toBeCloseTo(0.25, 1);
  expect(markBox.width / box.width).toBeCloseTo(0.4, 1);

  const thread = page.getByRole('article', { name: /^Comment 1 by / });
  await thread.getByRole('button', { name: 'Reply to comment 1' }).click();
  await page.getByRole('textbox', { name: 'Reply to comment 1' }).fill('Softened in v2.');
  await page.getByRole('button', { name: 'Post reply' }).click();
  await expect(thread.getByText('Softened in v2.')).toBeVisible();

  await thread.getByRole('button', { name: 'Resolve' }).click();
  await expect(page.getByText('Every comment on this version is resolved.')).toBeVisible();
  await expect(mark).toBeHidden();
  await page.getByRole('checkbox', { name: 'Show resolved (1)' }).check();
  await expect(thread.getByText(/^Resolved by /)).toBeVisible();

  // Still there after a reload: it is stored, not local state.
  await page.reload();
  await page.getByRole('tab', { name: 'Comments' }).click();
  await expect(page.getByRole('checkbox', { name: 'Show resolved (1)' })).toBeVisible();
});

test('with the keyboard alone, a region is marked, moved and commented on', async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(120_000);
  test.skip(testInfo.project.name !== 'desktop', 'a hardware keyboard journey');
  const asset = await seedImageAsset(request, uniqueName('comments_keys', testInfo));
  await openComments(page, asset.id);

  await page.getByRole('button', { name: 'Mark region' }).focus();
  await page.keyboard.press('Enter');
  // Its name says where it is, so find it by its place, then check the name as it changes.
  const draft = page.locator('.region-overlay__draft');
  await expect(draft).toBeFocused();
  await expect(draft).toHaveAccessibleName(
    'Marked region, 40 by 40 percent, 30 percent from the left and 30 from the top',
  );
  await page.keyboard.press('ArrowLeft');
  await page.keyboard.press('Shift+ArrowDown');
  await expect(draft).toHaveAccessibleName(
    'Marked region, 40 by 42 percent, 28 percent from the left and 30 from the top',
  );
  await page.keyboard.press('Enter');
  await expect(page.getByRole('textbox', { name: 'New comment' })).toBeFocused();
  await page.keyboard.type('Keyboard note');
  // Tab past "Remove region" and "Mark again" to Post comment.
  const post = page.getByRole('button', { name: 'Post comment' });
  for (
    let step = 0;
    step < 5 && !(await post.evaluate((node) => node === document.activeElement));
    step += 1
  ) {
    await page.keyboard.press('Tab');
  }
  await expect(post).toBeFocused();
  await page.keyboard.press('Enter');

  const mark = page.getByRole('button', { name: 'Region 1: Keyboard note' });
  await expect(mark).toBeVisible();
  await mark.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('article', { name: /^Comment 1 by / })).toBeFocused();
});

test('with the keyboard, deleting my comment leaves focus on its thread', async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(120_000);
  // KILN-48 (WCAG 2.4.3): "Delete comment" unmounts once the comment is gone, on both projects.
  const asset = await seedImageAsset(request, uniqueName('comments_delete', testInfo));
  const [versionId = ''] = await versionIdsOf(request, asset.id);
  await seedThread(request, versionId, { body: 'Posted by mistake.' });
  await openComments(page, asset.id);
  const thread = page.getByRole('article', { name: /^Comment 1 by / });

  await thread.getByRole('button', { name: 'Delete', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(thread.getByRole('button', { name: 'Delete comment' })).toBeFocused();
  await page.keyboard.press('Enter');

  await expect(thread.getByText('Comment deleted')).toBeVisible();
  await expect(thread).toBeFocused();
  expect(
    await thread.evaluate((node) => node === document.activeElement && node.tagName === 'ARTICLE'),
  ).toBe(true);
  // The focus outline sits outside the card's box: capture a margin around it.
  const box = await thread.boundingBox();
  if (!box) throw new Error('the thread has no box');
  await page.screenshot({
    path: `test-results/screens/kiln-48-thread-focused-${testInfo.project.name}.png`,
    clip: { x: box.x - 8, y: box.y - 8, width: box.width + 16, height: box.height + 16 },
  });
});

/** Records, on the field itself, what a screen reader meets at each `focusin`. */
const recordFocusIn = (field: Locator): Promise<void> =>
  field.evaluate((node) => {
    node.setAttribute('data-focusin', '[]');
    node.addEventListener('focusin', () => {
      const description = (node.getAttribute('aria-describedby') ?? '')
        .split(' ')
        .map((id) => document.getElementById(id)?.textContent ?? '')
        .join(' ')
        .trim();
      const seen = JSON.parse(node.getAttribute('data-focusin') ?? '[]') as string[];
      seen.push(`${String(node.getAttribute('aria-invalid'))} | ${description}`);
      node.setAttribute('data-focusin', JSON.stringify(seen));
    });
  });
const focusInRecords = async (field: Locator): Promise<string[]> =>
  JSON.parse((await field.getAttribute('data-focusin')) ?? '[]') as string[];

test('a failed new comment, reply or edit focuses its field once it says why, with no alert', async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(120_000);
  // KILN-48 review round 3: the API answers 500 to every write; each field must be aria-invalid
  // and describe the error when focus reaches it, and nothing else may announce it.
  const asset = await seedImageAsset(request, uniqueName('comments_failures', testInfo));
  const [versionId = ''] = await versionIdsOf(request, asset.id);
  await seedThread(request, versionId, { body: 'Mine to edit.' });
  await openComments(page, asset.id);
  await page.route('**/api/v1/**', async (route) => {
    if (!['POST', 'PATCH'].includes(route.request().method())) return route.continue();
    return route.fulfill({
      status: 500,
      contentType: 'application/problem+json',
      body: JSON.stringify({ type: 'about:blank', title: 'Down', status: 500, code: 'INTERNAL' }),
    });
  });
  const failedAt = async (field: Locator, submit: Locator): Promise<void> => {
    await recordFocusIn(field);
    await submit.click();
    await expect(field).toBeFocused();
    const [seen, ...more] = await focusInRecords(field);
    expect(more).toEqual([]);
    expect(seen).toMatch(/^true \| \S/);
    await expect(page.getByRole('alert')).toHaveCount(0);
  };

  const composer = page.getByRole('textbox', { name: 'New comment' });
  await composer.fill('Lost comment');
  await failedAt(composer, page.getByRole('button', { name: 'Post comment' }));

  const thread = page.getByRole('article', { name: /^Comment 1 by / });
  await thread.getByRole('button', { name: 'Reply to comment 1' }).click();
  const reply = thread.getByRole('textbox', { name: 'Reply to comment 1' });
  await reply.fill('Lost reply');
  await failedAt(reply, thread.getByRole('button', { name: 'Post reply' }));
  await page.keyboard.press('Escape');

  await thread.getByRole('button', { name: 'Edit', exact: true }).click();
  const edit = thread.getByRole('textbox', { name: 'Edit comment' });
  await edit.fill('Lost edit');
  await failedAt(edit, thread.getByRole('button', { name: 'Save' }));
});

test('with the keyboard, resolving a thread puts a visible focus on the list', async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(120_000);
  // KILN-48 review round 2: the thread leaves the list, so focus goes to the list region, which
  // must show the focus ring (WCAG 2.4.7) in both themes.
  const asset = await seedImageAsset(request, uniqueName('comments_resolve', testInfo));
  const [versionId = ''] = await versionIdsOf(request, asset.id);
  await seedThread(request, versionId, { body: 'Fix the rim.' });
  await openComments(page, asset.id);
  const thread = page.getByRole('article', { name: /^Comment 1 by / });

  await thread.getByRole('button', { name: 'Resolve' }).focus();
  await page.keyboard.press('Enter');

  const list = page.getByRole('region', { name: /^Comments on version / });
  await expect(thread).toBeHidden();
  await expect(list).toBeFocused();
  for (const theme of ['dark', 'light'] as const) {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    expect(
      await list.evaluate(
        (node) =>
          node.matches(':focus-visible') &&
          getComputedStyle(node).outlineStyle === 'solid' &&
          parseFloat(getComputedStyle(node).outlineWidth) >= 2,
      ),
    ).toBe(true);
    const box = await list.boundingBox();
    if (!box) throw new Error('the list has no box');
    await page.screenshot({
      path: `test-results/screens/kiln-48-list-focused-${testInfo.project.name}-${theme}.png`,
      clip: { x: box.x - 8, y: box.y - 8, width: box.width + 16, height: box.height + 16 },
    });
  }
});

test('with the keyboard, reopening a resolved thread keeps focus on its button', async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(120_000);
  // KILN-48 review round 1: Resolve and Reopen are one button; reopening must not lose focus.
  const asset = await seedImageAsset(request, uniqueName('comments_reopen', testInfo));
  const [versionId = ''] = await versionIdsOf(request, asset.id);
  const done = await seedThread(request, versionId, { body: 'Fixed in v2.' });
  await seedResolved(request, done.id);
  await openComments(page, asset.id);
  await page.getByRole('checkbox', { name: 'Show resolved (1)' }).check();
  const thread = page.getByRole('article', { name: /^Comment 1 by / });

  await thread.getByRole('button', { name: 'Reopen' }).focus();
  await page.keyboard.press('Enter');

  await expect(thread.getByText(/^Resolved by /)).toBeHidden();
  await expect(thread.getByRole('button', { name: 'Resolve' })).toBeFocused();
  expect(await page.evaluate(() => document.activeElement?.textContent?.trim())).toBe('Resolve');
});

const seedReview = async (
  request: Parameters<typeof seedImageAsset>[0],
  name: string,
): Promise<{ id: string }> => {
  const asset = await seedImageAsset(request, name);
  const [versionId = ''] = await versionIdsOf(request, asset.id);
  const first = await seedThread(request, versionId, {
    body: 'The swatch edge is too hard; soften the transition into the background.',
    region: { shape: 'rect', x: 0.1, y: 0.15, width: 0.45, height: 0.5 },
  });
  await seedThread(request, versionId, {
    body: 'This corner reads too saturated next to the UI.',
    region: { shape: 'point', x: 0.8, y: 0.3 },
  });
  await seedThread(request, versionId, {
    body: 'Overall: approved once the edge is fixed.\nThanks for the quick turnaround.',
  });
  const done = await seedThread(request, versionId, {
    body: 'Old note about the filename.',
    region: { shape: 'point', x: 0.5, y: 0.85 },
  });
  await seedResolved(request, done.id);
  for (const reply of [
    'Agreed — a 4 px feather should do.',
    'Tried 4 px; 6 px looks closer to the reference.',
    'Go with 6 px.',
  ]) {
    await seedReply(request, first.id, reply);
  }
  return asset;
};

test('moving focus back up never leaves it under the pinned preview (WCAG 2.4.11)', async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(120_000);
  test.skip(testInfo.project.name !== 'desktop', 'the preview is pinned on wide screens only');
  await page.setViewportSize({ width: 1440, height: 900 });
  const asset = await seedReview(request, uniqueName('comments_focus', testInfo));
  await openComments(page, asset.id);
  await page.getByRole('button', { name: 'Show 3 replies' }).click();
  const preview = page.locator('.asset-detail__preview--pinned');
  await expect(preview).toHaveCSS('position', 'sticky');
  // Down to the last thread's actions, then back up through every control of the panel.
  await page.getByRole('button', { name: 'Reply to comment 3' }).focus();
  for (let step = 0; step < 14; step += 1) {
    await page.keyboard.press('Shift+Tab');
    const covered = await page.evaluate(() => {
      const pinned = document.querySelector('.asset-detail__preview--pinned');
      const focused = document.activeElement;
      if (!pinned || !focused || pinned.contains(focused)) return 0;
      if (!focused.closest('.comments-panel')) return 0;
      return pinned.getBoundingClientRect().bottom - focused.getBoundingClientRect().top;
    });
    expect(covered, `step ${String(step)}`).toBeLessThanOrEqual(0);
  }
});

test('marks close together and a pin in the corner all stay reachable, inside the image', async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(120_000);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const asset = await seedImageAsset(request, uniqueName('comments_crowd', testInfo));
  const [versionId = ''] = await versionIdsOf(request, asset.id);
  const crowd = [
    { shape: 'rect', x: 0.5, y: 0.5, width: 0.2, height: 0.2 },
    { shape: 'rect', x: 0.51, y: 0.51, width: 0.2, height: 0.2 },
    { shape: 'point', x: 0.5, y: 0.5 },
    { shape: 'point', x: 0.505, y: 0.505 },
    { shape: 'point', x: 1, y: 1 },
    { shape: 'point', x: 0, y: 0 },
    { shape: 'rect', x: 0.99, y: 0.99, width: 0.01, height: 0.01 },
  ] as const;
  for (const [index, region] of crowd.entries()) {
    await seedThread(request, versionId, { body: `Mark ${String(index + 1)}`, region });
  }
  const overlay = await openComments(page, asset.id);
  const marks = page.getByRole('group', { name: 'Marked regions' }).getByRole('button');
  await expect(marks).toHaveCount(crowd.length);

  expect(await seriousViolations(page), 'crowded marks').toEqual([]);
  const image = await overlay.boundingBox();
  if (!image) throw new Error('no image box');
  const boxes = await marks.evaluateAll((buttons) =>
    buttons.map((button) => {
      const box = button.getBoundingClientRect();
      return { x: box.x, y: box.y, width: box.width, height: box.height };
    }),
  );
  for (const [index, box] of boxes.entries()) {
    expect(box.width, `mark ${String(index + 1)} width`).toBeGreaterThanOrEqual(24);
    expect(box.height, `mark ${String(index + 1)} height`).toBeGreaterThanOrEqual(24);
    expect(box.x, `mark ${String(index + 1)} left`).toBeGreaterThanOrEqual(image.x - 0.5);
    expect(box.y, `mark ${String(index + 1)} top`).toBeGreaterThanOrEqual(image.y - 0.5);
    expect(box.x + box.width).toBeLessThanOrEqual(image.x + image.width + 0.5);
    expect(box.y + box.height).toBeLessThanOrEqual(image.y + image.height + 0.5);
    for (const other of boxes.slice(index + 1)) {
      const apart =
        box.x + box.width <= other.x ||
        other.x + other.width <= box.x ||
        box.y + box.height <= other.y ||
        other.y + other.height <= box.y;
      expect(apart, `mark ${String(index + 1)} overlaps another`).toBe(true);
    }
  }
  await page.locator('.asset-detail__preview').screenshot({
    path: `test-results/screens/kiln-10-crowded-marks-${testInfo.project.name}.png`,
  });
  // Each one still opens its own thread.
  await marks.nth(3).click();
  await expect(page.getByRole('article', { name: /^Comment 4 by / })).toBeFocused();
});

test('a rectangle dragged along the right edge of the image posts', async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(120_000);
  const asset = await seedImageAsset(request, uniqueName('comments_edge', testInfo));
  const overlay = await openComments(page, asset.id);

  await page.getByRole('button', { name: 'Mark region' }).click();
  // A thin drag that starts a hair inside the right edge and ends past it.
  await drag(page, overlay, [0.998, 0.2, 1.2, 0.7]);
  await page.getByRole('textbox', { name: 'New comment' }).fill('Right edge');
  await page.getByRole('button', { name: 'Post comment' }).click();

  await expect(page.getByRole('button', { name: 'Region 1: Right edge' })).toBeVisible();
  await expect(page.getByText(/must lie on the image/)).toBeHidden();
});

for (const theme of ['dark', 'light'] as const) {
  test(`comments pass axe and never scroll sideways in the ${theme} theme`, async ({
    page,
    request,
  }, testInfo) => {
    test.setTimeout(120_000);
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    const asset = await seedReview(request, uniqueName(`comments_axe_${theme}`, testInfo));
    await openComments(page, asset.id);
    await expect(page.getByRole('button', { name: /^Region 2: / })).toBeVisible();
    await page.getByRole('button', { name: 'Show 3 replies' }).click();
    await expect(page.getByText('Go with 6 px.')).toBeVisible();

    expect(await seriousViolations(page), 'threads').toEqual([]);
    await page.getByRole('button', { name: 'Mark region' }).click();
    expect(await seriousViolations(page), 'marking').toEqual([]);
    const width = page.viewportSize()?.width ?? 0;
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    );
  });
}

test('screenshots of the comments tab at 1440 and 390 px in both themes', async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(180_000);
  test.skip(testInfo.project.name !== 'desktop', 'one set of screenshots is enough');
  const asset = await seedReview(request, uniqueName('comments_shots', testInfo));
  for (const theme of ['dark', 'light'] as const) {
    for (const width of [1440, 390]) {
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.setViewportSize({ width, height: width > 600 ? 900 : 844 });
      await openComments(page, asset.id);
      await page.getByRole('button', { name: 'Show 3 replies' }).click();
      await expect(page.getByText('Go with 6 px.')).toBeVisible();
      await page.getByRole('button', { name: /^Region 1: / }).click();
      await page.screenshot({
        path: `test-results/screens/kiln-10-comments-${String(width)}-${theme}.png`,
        fullPage: true,
      });
    }
  }
  await page.getByRole('button', { name: 'Mark region' }).click();
  await page.screenshot({ path: 'test-results/screens/kiln-10-marking-390-light.png' });
});
