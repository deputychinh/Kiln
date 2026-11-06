import { composeStories } from '@storybook/react';

import { BROKEN_PREVIEW_SAMPLE } from '#storybook/sample.constant';
import { BadgeTone } from '#ui/enums/badge-tone.enum';
import { ButtonVariant } from '#ui/enums/button-variant.enum';
import { SkeletonShape } from '#ui/enums/skeleton-shape.enum';

type StoriesModule = Parameters<typeof composeStories>[0];

const storyModules = import.meta.glob<StoriesModule>('./components/*/*.stories.tsx', {
  eager: true,
});
const componentFiles = Object.keys(
  import.meta.glob('./components/*/*.tsx', { eager: false }),
).filter((path) => !/\.(test|stories)\.tsx$/.test(path));

const folderOf = (path: string): string => path.split('/')[2] ?? path;

// jsdom never loads images; emulate the browser's asynchronous 404 for the one missing sample
// (`AssetThumb` BrokenImage) by dispatching `error` once the image is in the document.
const failMissingSamples = new MutationObserver(() => {
  for (const image of document.querySelectorAll<HTMLImageElement>('img')) {
    if (image.getAttribute('src') === BROKEN_PREVIEW_SAMPLE && !image.dataset.failed) {
      image.dataset.failed = 'true';
      setTimeout(() => image.dispatchEvent(new Event('error')), 0);
    }
  }
});

beforeAll(() => {
  failMissingSamples.observe(document.body, { childList: true, subtree: true });
});

afterAll(() => {
  failMissingSamples.disconnect();
});

describe('Storybook coverage', () => {
  it('has a stories file for every component folder', () => {
    const withStories = new Set(Object.keys(storyModules).map(folderOf));
    const missing = componentFiles.map(folderOf).filter((folder) => !withStories.has(folder));
    expect(missing).toEqual([]);
  });

  describe.each(Object.entries(storyModules))('%s', (_path, module) => {
    // `run` mounts the story with the preview's decorators, then runs its `play` function.
    const stories = composeStories(module) as Record<string, { run: () => Promise<void> }>;
    it.each(Object.entries(stories))(
      '%s renders and its play function passes',
      async (_name, Story) => {
        await Story.run();
      },
    );
  });

  // AC2: every value of a component's enum prop has its own story.
  it.each([
    ['Badge', 'tone', Object.values(BadgeTone)],
    ['Button', 'variant', Object.values(ButtonVariant)],
    ['Skeleton', 'shape', Object.values(SkeletonShape)],
  ])('has a %s story for every %s', (component, prop, values) => {
    const module = storyModules[`./components/${component}/${component}.stories.tsx`];
    const stories = Object.values<{ args: Record<string, unknown> }>(composeStories(module!));
    const shown = new Set(stories.map((story) => story.args[prop]));
    expect(values.filter((value) => !shown.has(value))).toEqual([]);
  });
});
