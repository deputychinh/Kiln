import { AxeBuilder } from '@axe-core/playwright';
import { type APIRequestContext, expect, type Page, test } from '@playwright/test';

const THEMES = ['dark', 'light'];
const WCAG_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];
const BLOCKING_IMPACTS = new Set(['serious', 'critical']);

// Storybook reports each story's `play` and a11y result on its channel (`storyFinished`);
// record those events so a failing `play` fails this run too.
const recordStoryResults = (): void => {
  let channel: { on: (event: string, listener: (payload: unknown) => void) => void } | undefined;
  const target = window as unknown as { kilnStoryResults: unknown[] };
  target.kilnStoryResults = [];
  Object.defineProperty(window, '__STORYBOOK_ADDONS_CHANNEL__', {
    configurable: true,
    get: () => channel,
    set: (value: NonNullable<typeof channel>) => {
      channel = value;
      value.on('storyFinished', (payload) => target.kilnStoryResults.push(payload));
    },
  });
};

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

// The BrokenImage story loads a missing sample on purpose; its 404 is the expected state.
const EXPECTED_CONSOLE_ERRORS: Record<string, RegExp> = {
  'components-assetthumb--broken-image': /Failed to load resource: .* 404/,
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
        expect.soft(await storyStatus(page), `${id} (${theme}) play and a11y`).toBe('success');
        const results = await new AxeBuilder({ page })
          .include('#storybook-root')
          .withTags(WCAG_TAGS)
          .analyze();
        const blocking = results.violations
          .filter((violation) => BLOCKING_IMPACTS.has(violation.impact ?? ''))
          .map((violation) => `${violation.id}: ${violation.help}`);
        expect.soft(blocking, `${id} (${theme})`).toEqual([]);
        const expected = EXPECTED_CONSOLE_ERRORS[id];
        const unexpected = consoleErrors.filter((text) => !expected?.test(text));
        expect.soft(unexpected, `${id} (${theme}) console`).toEqual([]);
      });
    }
  });
}

test('docs pages follow the theme and list the props with their descriptions', async ({
  page,
  request,
}) => {
  const ids = await entryIds(request, 'docs');
  expect(ids).toHaveLength(6);
  await page.goto('/iframe.html?id=components-errorstate--docs&viewMode=docs&globals=theme:light');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await expect(page.getByText('Render the title as a heading when the error is')).toBeVisible();
  await expect(page.locator('.docs-story').first()).toHaveCSS(
    'background-color',
    'rgb(246, 246, 244)',
  );
});
