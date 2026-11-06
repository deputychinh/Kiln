import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { UploadStatus } from '@/enums/upload-status.enum';
import { UploadPanel } from '@/features/uploads/components/UploadPanel';
import type { UploadItem, UploadsApi } from '@/interfaces/upload.interface';

const anItem = (overrides: Partial<UploadItem> = {}): UploadItem => ({
  id: 'row-1',
  file: new File(['x'], 'rock.png', { type: 'image/png' }),
  status: UploadStatus.Queued,
  progress: 0,
  error: null,
  canRetry: true,
  idempotencyKey: 'key-1',
  assetId: null,
  versionId: null,
  ...overrides,
});

const uploadsWith = (items: UploadItem[], outcomes: UploadItem[] = []): UploadsApi => ({
  items,
  outcomes,
  summary: {
    finished: items.filter((item) => item.status === UploadStatus.Ready).length,
    total: items.length,
  },
  add: vi.fn(),
  cancel: vi.fn(),
  retry: vi.fn(),
  remove: vi.fn(),
});

/** The panel inside a router, since a ready row links to its asset. */
const renderPanel = (uploads: UploadsApi) => {
  const router = createRouter({
    routeTree: createRootRoute({ component: () => <UploadPanel uploads={uploads} /> }),
    history: createMemoryHistory({ initialEntries: ['/assets'] }),
  });
  render(<RouterProvider router={router} />);
};

describe('UploadPanel', () => {
  it('passes dropped or picked files on and accepts only the supported types', async () => {
    const uploads = uploadsWith([]);
    renderPanel(uploads);
    const zone = await screen.findByRole('group', { name: 'Drop images or .glb files here' });
    const input = zone.querySelector<HTMLInputElement>('input[type="file"]')!;

    expect(input.accept).toBe(
      'image/png,image/jpeg,image/webp,model/gltf-binary,.png,.jpg,.jpeg,.webp,.glb',
    );
    await userEvent.upload(input, new File(['x'], 'crate.glb'));
    expect(uploads.add).toHaveBeenCalledWith([expect.objectContaining({ name: 'crate.glb' })]);
    expect(screen.queryByRole('list', { name: 'Uploads' })).not.toBeInTheDocument();
  });

  it('shows a running upload with its percent, a named progress bar and a named Cancel', async () => {
    const uploads = uploadsWith([anItem({ status: UploadStatus.Uploading, progress: 42.4 })]);
    renderPanel(uploads);

    const row = within(await screen.findByRole('list', { name: 'Uploads' })).getByRole('listitem');
    expect(within(row).getByText('Uploading 42 %')).toBeInTheDocument();
    expect(within(row).getByRole('progressbar', { name: 'Uploading rock.png' })).toHaveAttribute(
      'aria-valuenow',
      '42',
    );
    await userEvent.click(within(row).getByRole('button', { name: 'Cancel rock.png' }));
    expect(uploads.cancel).toHaveBeenCalledWith('row-1');
    expect(within(row).queryByRole('button', { name: /Remove/ })).not.toBeInTheDocument();
    expect(screen.getByText('0 of 1 uploaded')).toBeInTheDocument();
  });

  it('offers Retry and Remove for a failed upload, with its reason', async () => {
    const uploads = uploadsWith([
      anItem({ status: UploadStatus.Failed, error: 'Storage refused the file. Try again.' }),
    ]);
    renderPanel(uploads);

    expect(await screen.findByText('Storage refused the file. Try again.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Retry rock.png' }));
    await userEvent.click(screen.getByRole('button', { name: 'Remove rock.png' }));
    expect(uploads.retry).toHaveBeenCalledWith('row-1');
    expect(uploads.remove).toHaveBeenCalledWith('row-1');
  });

  it('offers only Remove when retrying cannot help', async () => {
    renderPanel(
      uploadsWith([
        anItem({ status: UploadStatus.Failed, error: 'This file is empty.', canRetry: false }),
      ]),
    );

    expect(await screen.findByRole('button', { name: 'Remove rock.png' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Retry/ })).not.toBeInTheDocument();
  });

  it('lets a cancelled upload be retried', async () => {
    renderPanel(uploadsWith([anItem({ status: UploadStatus.Cancelled })]));

    expect(await screen.findByRole('button', { name: 'Retry rock.png' })).toBeInTheDocument();
    expect(screen.getByText('Cancelled')).toBeInTheDocument();
  });

  it('shows processing with a full bar and no actions', async () => {
    renderPanel(uploadsWith([anItem({ status: UploadStatus.Processing, progress: 100 })]));

    const row = within(await screen.findByRole('list', { name: 'Uploads' })).getByRole('listitem');
    expect(within(row).getByText('Processing preview…')).toBeInTheDocument();
    expect(within(row).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100');
    expect(within(row).queryByRole('button')).not.toBeInTheDocument();
  });

  it('links a ready upload to its asset', async () => {
    renderPanel(uploadsWith([anItem({ status: UploadStatus.Ready, assetId: 'asset-1' })]));

    expect(await screen.findByRole('link', { name: 'rock.png' })).toHaveAttribute(
      'href',
      '/assets/asset-1',
    );
    expect(screen.getByText('1 of 1 uploaded')).toBeInTheDocument();
  });

  it('announces the files that just ended, once, politely', async () => {
    const ready = anItem({ status: UploadStatus.Ready });
    const failed = anItem({
      id: 'row-2',
      status: UploadStatus.Failed,
      error: 'This file is empty.',
      file: new File([], 'empty.png'),
    });
    renderPanel(uploadsWith([ready, failed], [ready, failed]));

    const live = (await screen.findByText(/rock.png: Ready/)).closest('[aria-live]');
    expect(live).toHaveAttribute('aria-live', 'polite');
    expect(live).toHaveTextContent('rock.png: Ready. empty.png: This file is empty.');
  });
});
