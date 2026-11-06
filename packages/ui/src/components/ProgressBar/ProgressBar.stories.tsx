import type { Meta, StoryObj } from '@storybook/react-vite';

import { withCardWidth } from '#storybook/decorators';
import { ProgressBar } from '#ui/components/ProgressBar/ProgressBar';

const meta = {
  title: 'Components/ProgressBar',
  component: ProgressBar,
  args: { label: 'Uploading crate_albedo.png', value: 0 },
  argTypes: { value: { control: { type: 'range', min: 0, max: 100, step: 1 } } },
  decorators: [withCardWidth],
} satisfies Meta<typeof ProgressBar>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Started: Story = {};

export const Halfway: Story = { args: { value: 50 } };

export const Complete: Story = { args: { value: 100 } };

export const WithValueText: Story = { args: { value: 40, valueText: '40 %, 4 of 10 MB' } };
