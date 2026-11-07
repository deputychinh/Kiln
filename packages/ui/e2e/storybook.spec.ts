import { AxeBuilder } from '@axe-core/playwright';
import { type APIRequestContext, expect, type Page, test } from '@playwright/test';

const THEMES = ['dark', 'light'];
const WCAG_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];
const BLOCKING_IMPACTS = new Set(['serious', 'critical']);

// Storybook reports on its channel when a story's `play` throws (`playFunctionThrewException`)
// and when it has finished with the a11y addon's verdict (`storyFinished`); record both.
const recordStoryResults = (): void => {
  let channel: { on: (event: string, listener: (payload: unknown) => void) => void } | undefined;
  const target = window as unknown as { kilnStoryResults: unknown[]; kilnPlayErrors: unknown[] };
  target.kilnStoryResults = [];
  target.kilnPlayErrors = [];
  Object.defineProperty(window, '__STORYBOOK_ADDONS_CHANNEL__', {
    configurable: true,
    get: () => channel,
    set: (value: NonNullable<typeof channel>) => {
      channel = value;
      value.on('storyFinished', (payload) => target.kilnStoryResults.push(payload));
      value.on('playFunctionThrewException', (error) =>
        target.kilnPlayErrors.push(String((error as { message?: string }).message ?? error)),
      );
    },
  });
};

const playErrors = (page: Page): Promise<string[]> =>
  page.evaluate(() => (window as unknown as { kilnPlayErrors: string[] }).kilnPlayErrors);

// Bounded per story, so a story that never finishes cannot use up the run for the rest.
const STORY_TIMEOUT_MS = 10_000;
const CHECK_TIMEOUT_MS = 2_000;

const storyStatus = async (page: Page): Promise<string> => {
  try {
    const handle = await page.waitForFunction(
      () => {
        const [result] = (window as unknown as { kilnStoryResults: { status: string }[] })
          .kilnStoryResults;
        return result?.status;
      },
      undefined,
      { timeout: STORY_TIMEOUT_MS },
    );
    return (await handle.jsonValue()) as string;
  } catch {
    return 'did not finish';
  }
};

const entryIds = async (request: APIRequestContext, type: string): Promise<string[]> => {
  const response = await request.get('/index.json');
  expect(response.ok()).toBe(true);
  const index = (await response.json()) as {
    entries: Record<string, { id: string; type: string }>;
  };
  return Object.values(index.entries)
    .filter((entry) => entry.type === type)
    .map((entry) => entry.id);
};

for (const theme of THEMES) {
  test(`every story renders without errors and passes axe in the ${theme} theme`, async ({
    page,
    request,
  }) => {
    await page.addInitScript(recordStoryResults);
    const ids = await entryIds(request, 'story');
    expect(ids.length).toBeGreaterThan(0);
    // Enough for the worst case: every story fails every bounded check and still gets axe.
    test.setTimeout(30_000 + ids.length * (STORY_TIMEOUT_MS + 3 * CHECK_TIMEOUT_MS + 5_000));
    const consoleErrors: string[] = [];
    page.on('console', (message) => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    page.on('pageerror', (error) => consoleErrors.push(error.message));

    for (const id of ids) {
      await test.step(id, async () => {
        consoleErrors.length = 0;
        await page.goto(`/iframe.html?id=${id}&viewMode=story&globals=theme:${theme}`);
        // Soft: one broken story must not hide the state of the ones after it.
        const check = { timeout: CHECK_TIMEOUT_MS };
        await expect.soft(page.locator('body'), `${id} renders`).toHaveClass(/sb-show-main/, check);
        await expect.soft(page.locator('body')).not.toHaveClass(/sb-show-errordisplay/, check);
        await expect.soft(page.locator('html')).toHaveAttribute('data-theme', theme, check);
        expect.soft(await storyStatus(page), `${id} (${theme}) a11y`).toBe('success');
        expect.soft(await playErrors(page), `${id} (${theme}) play`).toEqual([]);
        const results = await new AxeBuilder({ page })
          .include('#storybook-root')
          .withTags(WCAG_TAGS)
          .analyze();
        const blocking = results.violations
          .filter((violation) => BLOCKING_IMPACTS.has(violation.impact ?? ''))
          .map((violation) => `${violation.id}: ${violation.help}`);
        expect.soft(blocking, `${id} (${theme})`).toEqual([]);
        expect.soft(consoleErrors, `${id} (${theme}) console`).toEqual([]);
      });
    }
  });
}

// AC4: every docs page lists exactly its component's props. The component's own props must carry a
// description from their JSDoc; Button also passes on native `disabled`/`type` and its stories wire
// the native `onClick` to an action (React's types have no descriptions for those).
const DOCUMENTED_PROPS: Record<string, { own: string[]; native?: string[] }> = {
  'components-assetthumb--docs': { own: ['src', 'alt', 'placeholder', 'isEager', 'onError'] },
  'components-badge--docs': { own: ['tone', 'icon', 'children'] },
  'components-button--docs': {
    own: ['variant', 'icon', 'children', 'ref'],
    native: ['disabled', 'type', 'onClick'],
  },
  'components-dropoverlay--docs': { own: ['title', 'targets', 'onDrop', 'isEnabled'] },
  'components-emptystate--docs': { own: ['title', 'titleAs', 'icon', 'children', 'action'] },
  'components-errorstate--docs': {
    own: ['title', 'titleAs', 'message', 'retryLabel', 'onRetry', 'isRetrying', 'action'],
  },
  'components-filepickerbutton--docs': {
    own: [
      'children',
      'accessibleName',
      'icon',
      'variant',
      'accept',
      'isMultiple',
      'onFiles',
      'ref',
      'id',
    ],
  },
  'components-iconbutton--docs': {
    own: ['label', 'icon', 'variant', 'size', 'isPressed', 'tooltipPlacement', 'ref'],
    native: ['disabled', 'type', 'onClick'],
  },
  'components-progressbar--docs': { own: ['label', 'value', 'valueText'] },
  'components-segmentedcontrol--docs': {
    own: ['label', 'isLabelHidden', 'name', 'value', 'options', 'isIconOnly', 'onChange'],
  },
  'components-skeleton--docs': { own: ['shape'] },
  'components-statusdot--docs': { own: ['tone', 'isActive', 'children'] },
  'components-tabs--docs': {
    own: ['label', 'tabs', 'defaultSelectedId', 'selectedId', 'onSelect'],
  },
  'components-toolbar--docs': { own: ['label', 'children', 'end'] },
  'components-tooltip--docs': { own: ['content', 'placement', 'isBlock', 'as', 'children'] },
};

test('every docs page lists and describes every prop of its component', async ({
  page,
  request,
}) => {
  const ids = await entryIds(request, 'docs');
  expect(ids.sort()).toEqual(Object.keys(DOCUMENTED_PROPS).sort());
  for (const id of ids) {
    const { own, native = [] } = DOCUMENTED_PROPS[id] ?? { own: [] };
    await page.goto(`/iframe.html?id=${id}&viewMode=docs`);
    await expect(page.locator('.docblock-argstable-body > tr').first()).toBeVisible();
    // A described row has the description block before the type summary in its second cell.
    const rows = await page.locator('.docblock-argstable-body > tr').evaluateAll((trs) =>
      trs.map((tr) => ({
        name: (tr.children[0]?.textContent ?? '').replace(/\*$/, '').trim(),
        isDescribed: (tr.children[1]?.children.length ?? 0) > 1,
      })),
    );
    expect.soft(rows.map((row) => row.name).sort(), id).toEqual([...own, ...native].sort());
    const undescribed = rows.filter((row) => own.includes(row.name) && !row.isDescribed);
    expect
      .soft(
        undescribed.map((row) => row.name),
        `${id} descriptions`,
      )
      .toEqual([]);
  }
});

test('docs pages follow the theme', async ({ page }) => {
  await page.goto('/iframe.html?id=components-errorstate--docs&viewMode=docs&globals=theme:light');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await expect(page.locator('.docs-story').first()).toHaveCSS(
    'background-color',
    'rgb(250, 250, 250)',
  );
});
