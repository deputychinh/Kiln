import type { Meta, StoryObj } from '@storybook/react-vite';
import { Images, Upload } from 'lucide-react';

import { Button } from '#ui/components/Button/Button';
import { EmptyState } from '#ui/components/EmptyState/EmptyState';
import { ICON_SIZE } from '#ui/constants/icon.constant';

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
    icon: <Images size={ICON_SIZE.lg} />,
    children: 'Upload a PNG, JPEG, WebP or .glb file, or drop files anywhere on this page.',
    action: <Button icon={<Upload size={ICON_SIZE.sm} />}>Upload files</Button>,
  },
};

export const PageHeading: Story = {
  args: {
    titleAs: 'h1',
    title: 'Nothing to compare yet',
    children: 'Add a second version to this asset to compare the two.',
  },
};
