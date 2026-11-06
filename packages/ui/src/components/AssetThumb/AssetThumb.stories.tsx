import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, fn, waitFor, within } from 'storybook/test';

import { AssetThumb } from '#ui/components/AssetThumb/AssetThumb';

// Inline sample previews: stories never fetch remote images.
const SWATCH = `data:image/svg+xml,${encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 4 4"><rect width="2" height="2" fill="#c0392b"/><rect x="2" width="2" height="2" fill="#2980b9"/><rect y="2" width="2" height="2" fill="#27ae60"/><rect x="2" y="2" width="2" height="2" fill="#f1c40f"/></svg>',
)}`;
const WIDE = `data:image/svg+xml,${encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 2"><rect width="8" height="2" fill="#8e44ad"/></svg>',
)}`;
// Not an image: the browser fails to decode it, so the placeholder and `onError` take over.
const BROKEN = 'data:image/png;base64,AAAA';

const meta = {
  title: 'Components/AssetThumb',
  component: AssetThumb,
  args: { src: SWATCH, alt: 'crate_albedo.png', placeholder: 'Image', onError: fn() },
  // As in the app: a gallery card's width, on the card's raised surface.
  decorators: [
    (Story) => (
      <div
        style={{
          inlineSize: '12rem',
          padding: 'var(--kiln-space-2)',
          backgroundColor: 'var(--kiln-color-surface-raised)',
          borderRadius: 'var(--kiln-radius-lg)',
        }}
      >
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof AssetThumb>;

export default meta;
type Story = StoryObj<typeof meta>;

export const WithImage: Story = {};

export const NonSquareImage: Story = { args: { src: WIDE, alt: 'banner_wide.png' } };

export const NoPreview: Story = { args: { src: null, alt: '', placeholder: '3D model' } };

export const BrokenImage: Story = {
  args: { src: BROKEN, alt: 'missing.png' },
  play: async ({ args, canvasElement }) => {
    const canvas = within(canvasElement);
    await waitFor(() => expect(canvas.getByText('Image')).toBeVisible());
    await expect(canvas.queryByRole('img')).not.toBeInTheDocument();
    await expect(args.onError).toHaveBeenCalledTimes(1);
    await expect(args.onError).toHaveBeenCalledWith(BROKEN);
  },
};

export const Eager: Story = { args: { isEager: true } };
