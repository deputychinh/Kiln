import { composeStories } from '@storybook/react';

type StoriesModule = Parameters<typeof composeStories>[0];

const storyModules = import.meta.glob<StoriesModule>('./components/*/*.stories.tsx', {
  eager: true,
});
const componentFiles = Object.keys(
  import.meta.glob('./components/*/*.tsx', { eager: false }),
).filter((path) => !/\.(test|stories)\.tsx$/.test(path));

const folderOf = (path: string): string => path.split('/')[2] ?? path;

// jsdom never decodes images, so a browser's verdict on the one undecodable sample
// (`AssetThumb` BrokenImage) is emulated: complete with no pixels, i.e. broken.
const UNDECODABLE_SAMPLE = 'data:image/png;base64,AAAA';

beforeAll(() => {
  vi.spyOn(HTMLImageElement.prototype, 'complete', 'get').mockImplementation(function (
    this: HTMLImageElement,
  ) {
    return this.getAttribute('src') === UNDECODABLE_SAMPLE;
  });
});

afterAll(() => {
  vi.restoreAllMocks();
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
});
