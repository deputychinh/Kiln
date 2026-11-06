import { composeStories } from '@storybook/react';

type StoriesModule = Parameters<typeof composeStories>[0];

const storyModules = import.meta.glob<StoriesModule>('./components/*/*.stories.tsx', {
  eager: true,
});
const componentFiles = Object.keys(
  import.meta.glob('./components/*/*.tsx', { eager: false }),
).filter((path) => !/\.(test|stories)\.tsx$/.test(path));

const folderOf = (path: string): string => path.split('/')[2] ?? path;

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
});
