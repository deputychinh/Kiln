import type { Meta, StoryObj } from '@storybook/react-vite';
import { Upload } from 'lucide-react';
import { expect, fn, userEvent } from 'storybook/test';

import { FilePickerButton } from '#ui/components/FilePickerButton/FilePickerButton';
import { ICON_SIZE } from '#ui/constants/icon.constant';
import { ButtonVariant } from '#ui/enums/button-variant.enum';

const meta = {
  title: 'Components/FilePickerButton',
  component: FilePickerButton,
  args: {
    children: 'Upload',
    icon: <Upload size={ICON_SIZE.sm} />,
    accept: 'image/png,image/jpeg,image/webp,.glb',
    onFiles: fn(),
  },
  argTypes: { variant: { control: 'inline-radio', options: Object.values(ButtonVariant) } },
} satisfies Meta<typeof FilePickerButton>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {
  play: async ({ args, canvasElement }) => {
    const input = canvasElement.querySelector<HTMLInputElement>('input[type="file"]');
    if (!input) throw new Error('The picker has no file input');
    await userEvent.upload(input, new File(['x'], 'crate.glb', { type: '' }));
    await expect(args.onFiles).toHaveBeenCalledTimes(1);
  },
};

export const SecondarySingleFile: Story = {
  args: {
    variant: ButtonVariant.Secondary,
    children: 'Upload new version',
    accessibleName: 'Upload new version of rock_albedo',
    isMultiple: false,
  },
};
