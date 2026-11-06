import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, fn, userEvent, within } from 'storybook/test';

import { Button } from '#ui/components/Button/Button';
import { ButtonVariant } from '#ui/enums/button-variant.enum';

const meta = {
  title: 'Components/Button',
  component: Button,
  args: { children: 'Upload asset', onClick: fn() },
  argTypes: { variant: { control: 'inline-radio', options: Object.values(ButtonVariant) } },
} satisfies Meta<typeof Button>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {
  args: { variant: ButtonVariant.Primary },
  play: async ({ args, canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole('button', { name: 'Upload asset' }));
    await expect(args.onClick).toHaveBeenCalledTimes(1);
  },
};

export const Secondary: Story = {
  args: { variant: ButtonVariant.Secondary, children: 'Try again' },
};

export const Ghost: Story = { args: { variant: ButtonVariant.Ghost, children: 'Back to assets' } };

export const Disabled: Story = {
  args: { disabled: true },
  play: async ({ args, canvasElement }) => {
    const button = within(canvasElement).getByRole('button', { name: 'Upload asset' });
    await expect(button).toBeDisabled();
    await userEvent.click(button);
    await expect(args.onClick).not.toHaveBeenCalled();
  },
};
