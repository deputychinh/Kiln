import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, fn, userEvent, within } from 'storybook/test';

import { Button } from '#ui/components/Button/Button';
import { ErrorState } from '#ui/components/ErrorState/ErrorState';
import { ButtonVariant } from '#ui/enums/button-variant.enum';

const meta = {
  title: 'Components/ErrorState',
  component: ErrorState,
  args: {
    title: 'Cannot reach the API',
    message: 'Check your connection, then try again.',
    retryLabel: 'Try again',
  },
  argTypes: { titleAs: { control: 'inline-radio', options: ['p', 'h1', 'h2'] } },
} satisfies Meta<typeof ErrorState>;

export default meta;
type Story = StoryObj<typeof meta>;

export const WithRetry: Story = {
  args: { onRetry: fn() },
  play: async ({ args, canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole('button', { name: 'Try again' }));
    await expect(args.onRetry).toHaveBeenCalledTimes(1);
  },
};

export const Retrying: Story = {
  args: { onRetry: fn(), isRetrying: true },
  play: async ({ args, canvasElement }) => {
    const retry = within(canvasElement).getByRole('button', { name: 'Try again' });
    await expect(retry).toHaveAttribute('aria-disabled', 'true');
    await userEvent.click(retry);
    await expect(args.onRetry).not.toHaveBeenCalled();
  },
};

export const WithoutRetry: Story = {
  args: {
    title: 'This asset was not found',
    message: 'It may have been deleted.',
    action: <Button variant={ButtonVariant.Ghost}>Back to assets</Button>,
  },
};

export const PageLevel: Story = { args: { titleAs: 'h1', onRetry: fn() } };
