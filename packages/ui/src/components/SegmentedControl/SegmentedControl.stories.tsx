import type { Meta, StoryObj } from '@storybook/react-vite';
import { Box, Image, LayoutGrid, Rows3 } from 'lucide-react';
import { type ComponentProps, type ReactElement, useState } from 'react';
import { expect, fn, userEvent, within } from 'storybook/test';

import { SegmentedControl } from '#ui/components/SegmentedControl/SegmentedControl';
import { ICON_SIZE } from '#ui/constants/icon.constant';

/** Keeps the chosen value, as the app keeps it in the URL. */
const Controlled = (props: ComponentProps<typeof SegmentedControl<string>>): ReactElement => {
  const [value, setValue] = useState(props.value);
  return (
    <SegmentedControl
      {...props}
      value={value}
      onChange={(next) => {
        props.onChange(next);
        setValue(next);
      }}
    />
  );
};

const meta = {
  title: 'Components/SegmentedControl',
  component: SegmentedControl,
  args: {
    label: 'Kind',
    name: 'kind',
    value: 'all',
    onChange: fn(),
    options: [
      { value: 'all', label: 'All' },
      { value: 'image', label: 'Images', icon: <Image size={ICON_SIZE.sm} /> },
      { value: 'model', label: 'Models', icon: <Box size={ICON_SIZE.sm} /> },
    ],
  },
  render: (args) => <Controlled {...args} />,
} satisfies Meta<typeof SegmentedControl<string>>;

export default meta;
type Story = StoryObj<typeof meta>;

export const WithLabel: Story = {
  play: async ({ args, canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole('radio', { name: 'Models' }));
    await expect(args.onChange).toHaveBeenCalledWith('model');
  },
};

export const LabelHidden: Story = { args: { isLabelHidden: true } };

export const IconOnly: Story = {
  args: {
    label: 'Card size',
    name: 'size',
    value: 'large',
    isLabelHidden: true,
    isIconOnly: true,
    options: [
      { value: 'large', label: 'Large cards', icon: <LayoutGrid size={ICON_SIZE.sm} /> },
      { value: 'small', label: 'Small cards', icon: <Rows3 size={ICON_SIZE.sm} /> },
    ],
  },
};

export const WithDisabledOption: Story = {
  args: {
    label: 'View',
    name: 'mode',
    value: 'side',
    options: [
      { value: 'side', label: 'Side by side' },
      { value: 'swipe', label: 'Swipe', isDisabled: true },
    ],
  },
};
