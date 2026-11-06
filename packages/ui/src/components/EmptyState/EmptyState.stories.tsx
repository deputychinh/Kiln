import type { Meta, StoryObj } from '@storybook/react-vite';

import { Button } from '#ui/components/Button/Button';
import { EmptyState } from '#ui/components/EmptyState/EmptyState';

const meta = {
  title: 'Components/EmptyState',
  component: EmptyState,
  args: { title: 'No assets yet' },
} satisfies Meta<typeof EmptyState>;

export default meta;
type Story = StoryObj<typeof meta>;

export const TitleOnly: Story = {};

export const WithBody: Story = {
  args: { children: 'Upload a PNG, JPEG, WebP or .glb file to see it here.' },
};

export const WithAction: Story = {
  args: {
    children: 'Upload a PNG, JPEG, WebP or .glb file to see it here.',
    action: <Button>Upload asset</Button>,
  },
};
