import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, fn, userEvent, within } from 'storybook/test';

import { Tabs } from '#ui/components/Tabs/Tabs';

const meta = {
  title: 'Components/Tabs',
  component: Tabs,
  args: {
    label: 'Asset sections',
    onSelect: fn(),
    tabs: [
      { id: 'versions', label: 'Versions', badge: 3, panel: <p>Version 3 · Ready</p> },
      { id: 'info', label: 'Info', panel: <p>Kind: Image</p> },
    ],
  },
} satisfies Meta<typeof Tabs>;

export default meta;
type Story = StoryObj<typeof meta>;

export const FirstOpen: Story = {};

/** Keyboard: one tab stop, the arrow keys open the next tab. */
export const KeyboardNavigation: Story = {
  play: async ({ args, canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.tab();
    await userEvent.keyboard('{ArrowRight}');
    await expect(canvas.getByRole('tab', { name: 'Info' })).toHaveFocus();
    await expect(canvas.getByRole('tabpanel', { name: 'Info' })).toHaveTextContent('Kind: Image');
    await expect(args.onSelect).toHaveBeenCalledWith('info');
  },
};

export const SecondOpen: Story = { args: { defaultSelectedId: 'info' } };
