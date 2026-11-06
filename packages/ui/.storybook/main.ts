import type { StorybookConfig } from '@storybook/react-vite';

// Dev/build tool only: the static build is not deployed in v0.1 (public Storybook is KILN-20).
const config: StorybookConfig = {
  framework: '@storybook/react-vite',
  stories: ['../src/**/*.stories.tsx'],
  addons: ['@storybook/addon-docs', '@storybook/addon-a11y'],
  core: { disableTelemetry: true, disableWhatsNewNotifications: true },
  typescript: {
    reactDocgen: 'react-docgen-typescript',
    reactDocgenTypescriptOptions: {
      // Document `children` and the native props a component passes on (`disabled`, `type`),
      // not the hundreds of other inherited DOM attributes.
      skipChildrenPropWithoutDoc: false,
      propFilter: (prop) =>
        !prop.parent?.fileName.includes('node_modules') || ['disabled', 'type'].includes(prop.name),
    },
  },
};

export default config;
