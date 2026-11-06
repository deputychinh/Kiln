import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, fn, userEvent } from 'storybook/test';

import { Dropzone } from '#ui/components/Dropzone/Dropzone';

const meta = {
  title: 'Components/Dropzone',
  component: Dropzone,
  args: {
    label: 'Drop images or .glb files here',
    buttonLabel: 'Choose files',
    accept: 'image/png,image/jpeg,image/webp,.glb',
    onFiles: fn(),
  },
} satisfies Meta<typeof Dropzone>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: { hint: 'PNG, JPEG, WebP or .glb, up to 500 MB each' },
  play: async ({ args, canvasElement }) => {
    const input = canvasElement.querySelector<HTMLInputElement>('input[type="file"]');
    if (!input) throw new Error('The dropzone has no file input');
    await userEvent.upload(input, new File(['x'], 'crate.glb', { type: '' }));
    await expect(args.onFiles).toHaveBeenCalledTimes(1);
  },
};

export const WithoutHint: Story = {};
