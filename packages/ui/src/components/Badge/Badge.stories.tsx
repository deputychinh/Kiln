import type { Meta, StoryObj } from '@storybook/react-vite';
import { Box } from 'lucide-react';

import { Badge } from '#ui/components/Badge/Badge';
import { ICON_SIZE } from '#ui/constants/icon.constant';
import { BadgeTone } from '#ui/enums/badge-tone.enum';

const meta = {
  title: 'Components/Badge',
  component: Badge,
  args: { children: 'Image' },
  argTypes: { tone: { control: 'inline-radio', options: Object.values(BadgeTone) } },
} satisfies Meta<typeof Badge>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Neutral: Story = { args: { tone: BadgeTone.Neutral } };

export const Info: Story = { args: { tone: BadgeTone.Info, children: 'Processing' } };

export const Success: Story = { args: { tone: BadgeTone.Success, children: 'Ready' } };

export const Warning: Story = { args: { tone: BadgeTone.Warning, children: 'Pending' } };

export const Danger: Story = { args: { tone: BadgeTone.Danger, children: 'Failed' } };

export const WithIcon: Story = {
  args: { tone: BadgeTone.Neutral, children: 'Model', icon: <Box size={ICON_SIZE.sm} /> },
};
