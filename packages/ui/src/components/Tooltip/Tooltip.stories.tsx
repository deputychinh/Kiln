import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, within } from 'storybook/test';

import { Tooltip } from '#ui/components/Tooltip/Tooltip';
import { TooltipPlacement } from '#ui/enums/tooltip-placement.enum';

const meta = {
  title: 'Components/Tooltip',
  component: Tooltip,
  args: {
    content: 'sunset_matte_painting_background_v3_final.png',
    children: <button type="button">sunset_matte…final.png</button>,
  },
  argTypes: { placement: { control: 'inline-radio', options: Object.values(TooltipPlacement) } },
  parameters: { layout: 'centered' },
} satisfies Meta<typeof Tooltip>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Top: Story = { args: { placement: TooltipPlacement.Top } };

export const Bottom: Story = { args: { placement: TooltipPlacement.Bottom } };

export const End: Story = { args: { placement: TooltipPlacement.End } };

export const BottomEnd: Story = { args: { placement: TooltipPlacement.BottomEnd } };

/** Keyboard focus shows it; Escape hides it and focus stays on the trigger (WCAG 1.4.13). */
export const DismissedWithEscape: Story = {
  play: async ({ canvasElement }) => {
    const trigger = within(canvasElement).getByRole('button');
    await userEvent.tab();
    await expect(trigger).toHaveFocus();
    await userEvent.keyboard('{Escape}');
    await expect(trigger.parentElement).toHaveClass('tooltip--dismissed');
    await expect(trigger).toHaveFocus();
  },
};
