import type { Decorator } from '@storybook/react-vite';

/** A gallery card's width, for components that fill their container. */
export const withCardWidth: Decorator = (Story) => (
  <div className="story-frame">
    <Story />
  </div>
);

/** A gallery card's width on the card's raised surface, as previews appear in the app. */
export const withCardSurface: Decorator = (Story) => (
  <div className="story-frame story-frame--raised">
    <Story />
  </div>
);
