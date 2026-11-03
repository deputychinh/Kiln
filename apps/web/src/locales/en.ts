import type { Copy } from '@/interfaces/copy.interface';

export const en: Copy = {
  app: {
    name: 'Kiln',
    tagline: 'Review and publish creative assets with your studio.',
    skipToContent: 'Skip to content',
  },
  health: {
    checking: 'Checking the API…',
    ok: (version) => `API online · v${version}`,
    down: 'The API is not reachable.',
    retry: 'Try again',
  },
};
