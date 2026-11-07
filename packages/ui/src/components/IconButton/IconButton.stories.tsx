import type { Meta, StoryObj } from '@storybook/react-vite';
import { LayoutGrid, Moon, Upload } from 'lucide-react';
import { expect, fn, userEvent, within } from 'storybook/test';

import { IconButton } from '#ui/components/IconButton/IconButton';
import { ICON_SIZE } from '#ui/constants/icon.constant';
import { ButtonVariant } from '#ui/enums/button-variant.enum';
import { IconButtonSize } from '#ui/enums/icon-button-size.enum';

const meta = {
  title: 'Components/IconButton',
  component: IconButton,
  args: { label: 'Switch to dark theme', icon: <Moon size={ICON_SIZE.md} />, onClick: fn() },
  argTypes: {
    variant: { control: 'inline-radio', options: Object.values(ButtonVariant) },
    size: { control: 'inline-radio', options: Object.values(IconButtonSize) },
  },
  // Room for the tooltip below the button.
  parameters: { layout: 'centered' },
} satisfies Meta<typeof IconButton>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Ghost: Story = {
  args: { variant: ButtonVariant.Ghost },
  play: async ({ args, canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole('button', { name: args.label }));
    await expect(args.onClick).toHaveBeenCalledTimes(1);
  },
};

export const Secondary: Story = { args: { variant: ButtonVariant.Secondary } };

export const Primary: Story = {
  args: {
    variant: ButtonVariant.Primary,
    size: IconButtonSize.Large,
    label: 'Upload',
    icon: <Upload size={ICON_SIZE.md} />,
  },
};

export const Small: Story = { args: { size: IconButtonSize.Small } };

export const Medium: Story = { args: { size: IconButtonSize.Medium } };

export const Pressed: Story = {
  args: { label: 'Large cards', icon: <LayoutGrid size={ICON_SIZE.md} />, isPressed: true },
};

export const Disabled: Story = { args: { disabled: true } };
