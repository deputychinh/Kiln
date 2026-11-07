import type { Meta, StoryObj } from '@storybook/react-vite';

import { StatusDot } from '#ui/components/StatusDot/StatusDot';
import { BadgeTone } from '#ui/enums/badge-tone.enum';

const meta = {
  title: 'Components/StatusDot',
  component: StatusDot,
  args: { children: 'Ready' },
  argTypes: { tone: { control: 'inline-radio', options: Object.values(BadgeTone) } },
} satisfies Meta<typeof StatusDot>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Neutral: Story = { args: { tone: BadgeTone.Neutral, children: 'Waiting for upload' } };

export const Info: Story = {
  args: { tone: BadgeTone.Info, children: 'Processing', isActive: true },
};

export const Success: Story = { args: { tone: BadgeTone.Success } };

export const Warning: Story = { args: { tone: BadgeTone.Warning, children: 'Cancelled' } };

export const Danger: Story = { args: { tone: BadgeTone.Danger, children: 'Failed' } };
