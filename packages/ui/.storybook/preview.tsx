import type { Decorator, Preview } from '@storybook/react-vite';

import '#ui/tokens/tokens.css';
import './preview.css';

// The app defaults to the dark token set; the toolbar switches `data-theme` like the app does.
const withTheme: Decorator = (Story, context) => {
  document.documentElement.dataset.theme = String(context.globals.theme ?? 'dark');
  return <Story />;
};

const preview: Preview = {
  tags: ['autodocs'],
  decorators: [withTheme],
  globalTypes: {
    theme: {
      description: 'Token theme',
      toolbar: {
        title: 'Theme',
        icon: 'contrast',
        items: [
          { value: 'dark', title: 'Dark' },
          { value: 'light', title: 'Light' },
        ],
        dynamicTitle: true,
      },
    },
  },
  initialGlobals: { theme: 'dark' },
  parameters: {
    layout: 'padded',
    controls: { expanded: true },
    // Fail the a11y panel (and the test pass) on violations instead of only listing them.
    a11y: { test: 'error' },
  },
};

export default preview;
