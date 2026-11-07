import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, within } from 'storybook/test';

import { TextField } from '#ui/components/TextField/TextField';

const meta = {
  title: 'Components/TextField',
  component: TextField,
  args: { label: 'Email', type: 'email', autoComplete: 'off' },
  decorators: [
    (Story) => (
      <div style={{ maxInlineSize: '24rem' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof TextField>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  play: async ({ canvasElement }) => {
    const input = within(canvasElement).getByRole('textbox', { name: 'Email' });
    await userEvent.type(input, 'ada@studio.com');
    await expect(input).toHaveValue('ada@studio.com');
  },
};

export const WithHint: Story = {
  args: { label: 'Token name', type: 'text', hint: 'Where you will use it, e.g. Blender laptop.' },
};

export const Invalid: Story = {
  args: { error: 'Enter your email.', hint: 'The address your studio gave you.' },
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).getByRole('textbox')).toHaveAttribute(
      'aria-invalid',
      'true',
    );
  },
};

export const Password: Story = { args: { label: 'Password', type: 'password' } };

export const ReadOnly: Story = {
  args: {
    label: 'Your new token',
    type: 'text',
    readOnly: true,
    value: 'kiln_pat_3fJ9xQ2mVb7L0pTzR1aYc8WnE5uKs6Hd4GiO2qXwM9e',
  },
};

export const Disabled: Story = { args: { disabled: true, value: 'ada@studio.com' } };
