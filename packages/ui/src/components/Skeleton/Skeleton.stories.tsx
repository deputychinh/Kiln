import type { Meta, StoryObj } from '@storybook/react-vite';

import { Skeleton } from '#ui/components/Skeleton/Skeleton';
import { SkeletonShape } from '#ui/enums/skeleton-shape.enum';

const meta = {
  title: 'Components/Skeleton',
  component: Skeleton,
  argTypes: { shape: { control: 'inline-radio', options: Object.values(SkeletonShape) } },
  // A skeleton fills its container; give it the width of a gallery card.
  decorators: [
    (Story) => (
      <div style={{ inlineSize: '12rem' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof Skeleton>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Line: Story = { args: { shape: SkeletonShape.Line } };

export const Tile: Story = { args: { shape: SkeletonShape.Tile } };
