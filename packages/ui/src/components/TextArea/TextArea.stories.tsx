import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';
import { expect, userEvent, within } from 'storybook/test';

import { TextArea } from '#ui/components/TextArea/TextArea';

const meta = {
  title: 'Components/TextArea',
  component: TextArea,
  args: { label: 'Comment', placeholder: 'What should change here?' },
  decorators: [
    (Story) => (
      <div style={{ maxInlineSize: '24rem' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof TextArea>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  play: async ({ canvasElement }) => {
    const field = within(canvasElement).getByRole('textbox', { name: 'Comment' });
    await userEvent.type(field, 'The rim is too bright.{enter}Try 80 %.');
    await expect(field).toHaveValue('The rim is too bright.\nTry 80 %.');
  },
};

export const WithHint: Story = {
  args: { hint: 'Line breaks are kept. Up to 2,000 characters.' },
};

const CountedTextArea = (args: Parameters<typeof TextArea>[0]) => {
  const [value, setValue] = useState('Warm the shadows a little.');
  return (
    <TextArea
      {...args}
      value={value}
      maxLength={2000}
      showCount
      onChange={(event) => setValue(event.target.value)}
    />
  );
};

/** The count needs a controlled value, so this story keeps its own state. */
export const WithCount: Story = {
  render: (args) => <CountedTextArea {...args} />,
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).getByText('26 / 2000')).toBeVisible();
  },
};

export const Invalid: Story = {
  args: { error: 'Write a comment first.' },
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).getByRole('textbox')).toHaveAttribute(
      'aria-invalid',
      'true',
    );
  },
};

export const HiddenLabel: Story = { args: { label: 'Reply to comment 2', isLabelHidden: true } };

export const Disabled: Story = { args: { disabled: true, value: 'Posting…' } };
