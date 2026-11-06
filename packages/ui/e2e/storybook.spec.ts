import { AxeBuilder } from '@axe-core/playwright';
import { type APIRequestContext, expect, test } from '@playwright/test';

const THEMES = ['dark', 'light'];
const WCAG_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];
const BLOCKING_IMPACTS = new Set(['serious', 'critical']);

const storyIds = async (request: APIRequestContext): Promise<string[]> => {
  const response = await request.get('/index.json');
  expect(response.ok()).toBe(true);
  const index = (await response.json()) as {
    entries: Record<string, { id: string; type: string }>;
  };
  return Object.values(index.entries)
    .filter((entry) => entry.type === 'story')
    .map((entry) => entry.id);
};

for (const theme of THEMES) {
  test(`every story renders without errors and passes axe in the ${theme} theme`, async ({
    page,
    request,
  }) => {
    test.setTimeout(120_000);
    const ids = await storyIds(request);
    expect(ids.length).toBeGreaterThan(0);
    const consoleErrors: string[] = [];
    page.on('console', (message) => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    page.on('pageerror', (error) => consoleErrors.push(error.message));

    for (const id of ids) {
      await test.step(id, async () => {
        consoleErrors.length = 0;
        await page.goto(`/iframe.html?id=${id}&viewMode=story&globals=theme:${theme}`);
        await expect(page.locator('body')).toHaveClass(/sb-show-main/);
        await expect(page.locator('body')).not.toHaveClass(/sb-show-errordisplay/);
        await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
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
