import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';

import { SegmentedControl } from '#ui/components/SegmentedControl/SegmentedControl';
import { Toolbar } from '#ui/components/Toolbar/Toolbar';

const KindFilter = () => {
  const [kind, setKind] = useState('all');
  return (
    <SegmentedControl
      label="Kind"
      isLabelHidden
      name="story-kind"
      value={kind}
      onChange={setKind}
      options={[
        { value: 'all', label: 'All' },
        { value: 'image', label: 'Images' },
        { value: 'model', label: 'Models' },
      ]}
    />
  );
};

const meta = {
  title: 'Components/Toolbar',
  component: Toolbar,
  args: {
    label: 'Gallery options',
    children: <strong>Assets · 24</strong>,
    end: <KindFilter />,
  },
} satisfies Meta<typeof Toolbar>;

export default meta;
type Story = StoryObj<typeof meta>;

export const WithControls: Story = {};

export const StartOnly: Story = { args: { end: undefined } };
