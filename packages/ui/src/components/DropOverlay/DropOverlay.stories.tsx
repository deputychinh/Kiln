import type { Meta, StoryObj } from '@storybook/react-vite';
import { ImagePlus, Layers } from 'lucide-react';
import { expect, fn, waitFor } from 'storybook/test';

import { DropOverlay } from '#ui/components/DropOverlay/DropOverlay';
import { ICON_SIZE } from '#ui/constants/icon.constant';

/** The overlay opens only while files are dragged over the window: the story starts such a drag. */
const startFileDrag = async (): Promise<void> => {
  // A plain event with a file-carrying `dataTransfer`: the same in browsers and in jsdom. Sent
  // until the overlay shows, since the window listener is attached after the first paint.
  await waitFor(() => {
    if (!document.querySelector('.drop-overlay')) {
      const enter = new Event('dragenter', { bubbles: true });
      Object.defineProperty(enter, 'dataTransfer', { value: { types: ['Files'], files: [] } });
      window.dispatchEvent(enter);
    }
    return expect(document.querySelector('.drop-overlay')).not.toBeNull();
  });
};

const meta = {
  title: 'Components/DropOverlay',
  component: DropOverlay,
  args: {
    title: 'Drop files to upload',
    onDrop: fn(),
    targets: [
      {
        id: 'assets',
        label: 'New assets',
        hint: 'PNG, JPEG, WebP or glTF binary (.glb), up to 500 MB each.',
        icon: <ImagePlus size={ICON_SIZE.lg} />,
      },
    ],
  },
  parameters: { layout: 'fullscreen' },
} satisfies Meta<typeof DropOverlay>;

export default meta;
type Story = StoryObj<typeof meta>;

export const OneTarget: Story = { play: startFileDrag };

export const TwoTargets: Story = {
  args: {
    targets: [
      { id: 'assets', label: 'New assets', icon: <ImagePlus size={ICON_SIZE.lg} /> },
      {
        id: 'version',
        label: 'New version of rock_albedo',
        hint: 'PNG, JPEG or WebP. Each file becomes the next version.',
        icon: <Layers size={ICON_SIZE.lg} />,
      },
    ],
  },
  play: startFileDrag,
};

/** Before any drag nothing shows: the Upload button is the visible way in. */
export const Idle: Story = {};
