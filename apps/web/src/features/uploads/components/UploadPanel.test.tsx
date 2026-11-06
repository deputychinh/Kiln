import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';

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

const uploadsWith = (
  items: UploadItem[],
  outcomes: UploadItem[] = [],
  outcomeCount = outcomes.length,
): UploadsApi => ({
  items,
  outcomes,
  outcomeCount,
  summary: {
    finished: items.filter((item) => item.status === UploadStatus.Ready).length,
    failed: items.filter((item) => item.status === UploadStatus.Failed).length,
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

/** The panel over a tiny in-memory queue, so Cancel, Retry and Remove change the rows. */
const StatefulPanel = ({ initial }: { initial: UploadItem[] }) => {
  const [items, setItems] = useState(initial);
  const set = (id: string, status: UploadStatus) =>
    setItems((rows) => rows.map((row) => (row.id === id ? { ...row, status } : row)));
  return (
    <UploadPanel
      uploads={{
        ...uploadsWith(items),
        cancel: (id) => set(id, UploadStatus.Cancelled),
        retry: (id) => set(id, UploadStatus.Queued),
        remove: (id) => setItems((rows) => rows.filter((row) => row.id !== id)),
      }}
    />
  );
};

const renderStateful = (initial: UploadItem[]) => {
  const router = createRouter({
    routeTree: createRootRoute({ component: () => <StatefulPanel initial={initial} /> }),
    history: createMemoryHistory({ initialEntries: ['/assets'] }),
  });
  render(<RouterProvider router={router} />);
};

/** The bare panel (no links rendered) for tests that rerender it with new rows. */
const StatefulOnly = ({
  items,
  outcomes = [],
}: {
  items: UploadItem[];
  outcomes?: UploadItem[];
}) => <UploadPanel uploads={uploadsWith(items, outcomes)} />;

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

  it('counts failed files in the summary', async () => {
    renderPanel(
      uploadsWith([
        anItem({ status: UploadStatus.Ready }),
        anItem({ id: 'row-2', status: UploadStatus.Failed, error: 'x' }),
      ]),
    );

    expect(await screen.findByText('1 of 2 uploaded, 1 failed')).toBeInTheDocument();
  });

  it('explains the empty asset a cancelled upload leaves behind', async () => {
    renderPanel(uploadsWith([anItem({ status: UploadStatus.Cancelled, assetId: 'asset-1' })]));

    expect(
      await screen.findByText('Cancelled. The empty asset it started is removed within 24 hours.'),
    ).toBeInTheDocument();
  });

  it('keeps keyboard focus in the row when Cancel turns into Retry, and Retry into Cancel', async () => {
    renderStateful([anItem({ status: UploadStatus.Uploading })]);

    await userEvent.click(await screen.findByRole('button', { name: 'Cancel rock.png' }));
    expect(await screen.findByRole('button', { name: 'Retry rock.png' })).toHaveFocus();

    await userEvent.click(screen.getByRole('button', { name: 'Retry rock.png' }));
    expect(await screen.findByRole('button', { name: 'Cancel rock.png' })).toHaveFocus();
  });

  it('moves focus to the next row after Remove, or to Choose files when the list is empty', async () => {
    renderStateful([
      anItem({ status: UploadStatus.Failed, error: 'x' }),
      anItem({
        id: 'row-2',
        status: UploadStatus.Failed,
        error: 'y',
        file: new File(['x'], 'tree.png'),
      }),
    ]);

    await userEvent.click(await screen.findByRole('button', { name: 'Remove rock.png' }));
    expect(await screen.findByRole('button', { name: 'Retry tree.png' })).toHaveFocus();

    await userEvent.click(screen.getByRole('button', { name: 'Remove tree.png' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Choose files' })).toHaveFocus());
  });

  it('lets a cancelled upload be retried', async () => {
    renderPanel(uploadsWith([anItem({ status: UploadStatus.Cancelled })]));

    expect(await screen.findByRole('button', { name: 'Retry rock.png' })).toBeInTheDocument();
    expect(screen.getByText('Cancelled')).toBeInTheDocument();
  });

  it('shows processing with a full bar and lets the row be dismissed', async () => {
    renderPanel(uploadsWith([anItem({ status: UploadStatus.Processing, progress: 100 })]));

    const row = within(await screen.findByRole('list', { name: 'Uploads' })).getByRole('listitem');
    expect(within(row).getByText('Processing preview…')).toBeInTheDocument();
    expect(within(row).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100');
    expect(
      within(row)
        .getAllByRole('button')
        .map((button) => button.textContent),
    ).toEqual(['Remove']);
  });

  it('links a ready upload to its asset', async () => {
    renderPanel(uploadsWith([anItem({ status: UploadStatus.Ready, assetId: 'asset-1' })]));

    expect(await screen.findByRole('link', { name: 'rock.png' })).toHaveAttribute(
      'href',
      '/assets/asset-1',
    );
    expect(screen.getByText('1 of 1 uploaded')).toBeInTheDocument();
  });

  it('refuses a file dropped outside the zone instead of letting the browser open it', async () => {
    renderPanel(uploadsWith([]));
    await screen.findByRole('button', { name: 'Choose files' });

    const drop = new Event('drop', { bubbles: true, cancelable: true });
    Object.defineProperty(drop, 'dataTransfer', {
      value: { types: ['Files'], dropEffect: 'copy' },
    });
    document.body.dispatchEvent(drop);
    const text = new Event('drop', { bubbles: true, cancelable: true });
    Object.defineProperty(text, 'dataTransfer', { value: { types: ['text/plain'] } });
    document.body.dispatchEvent(text);

    expect(drop.defaultPrevented).toBe(true);
    expect(text.defaultPrevented).toBe(false);
  });

  it('asks before the page is left while files are uploading, and not after', async () => {
    const { rerender } = render(
      <StatefulOnly items={[anItem({ status: UploadStatus.Uploading })]} />,
    );
    await screen.findByRole('button', { name: 'Choose files' });
    const busy = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(busy);
    expect(busy.defaultPrevented).toBe(true);

    rerender(<StatefulOnly items={[anItem({ status: UploadStatus.Ready })]} />);
    const idle = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(idle);
    expect(idle.defaultPrevented).toBe(false);
  });

  it('announces a repeated outcome again, outside the list pane', async () => {
    const ready = anItem({ status: UploadStatus.Ready });
    // Outcomes from before the panel mounted are not news; only later ones are announced.
    const { rerender } = render(<StatefulOnly items={[ready]} />);
    rerender(<StatefulOnly items={[ready]} outcomes={[ready]} />);
    const live = (await screen.findByText('rock.png: Ready.')).closest('[aria-live]');
    expect(live?.parentElement).toBe(document.body);

    rerender(<StatefulOnly items={[ready]} outcomes={[ready, { ...ready }]} />);
    expect(live).toHaveTextContent('');
    await waitFor(() => expect(live).toHaveTextContent('rock.png: Ready.'));
  });

  it('announces every outcome when files end in separate changes within one frame', async () => {
    const a = anItem({
      status: UploadStatus.Failed,
      error: 'Kiln is busy right now. Try again in a moment.',
    });
    const b = anItem({
      id: 'row-2',
      status: UploadStatus.Failed,
      error: 'This file is empty.',
      file: new File([], 'b.png'),
    });
    const c = anItem({
      id: 'row-3',
      status: UploadStatus.Processing,
      file: new File(['x'], 'c.png'),
    });
    const { rerender } = render(<StatefulOnly items={[a, b, c]} />);
    rerender(<StatefulOnly items={[a, b, c]} outcomes={[a]} />);
    rerender(<StatefulOnly items={[a, b, c]} outcomes={[a, b]} />);
    rerender(
      <StatefulOnly
        items={[a, b, { ...c, status: UploadStatus.Ready }]}
        outcomes={[a, b, { ...c, status: UploadStatus.Ready }]}
      />,
    );

    const live = document.body.querySelector('[aria-live="polite"]');
    await waitFor(() =>
      expect(live).toHaveTextContent(
        'rock.png: Kiln is busy right now. Try again in a moment. b.png: This file is empty. c.png: Ready.',
      ),
    );
  });

  it('announces the files that just ended, once, politely', async () => {
    const ready = anItem({ status: UploadStatus.Ready });
    const failed = anItem({
      id: 'row-2',
      status: UploadStatus.Failed,
      error: 'This file is empty.',
      file: new File([], 'empty.png'),
    });
    const { rerender } = render(<StatefulOnly items={[ready, failed]} />);
    rerender(<StatefulOnly items={[ready, failed]} outcomes={[ready, failed]} />);

    const live = (await screen.findByText(/rock.png: Ready/)).closest('[aria-live]');
    expect(live).toHaveAttribute('aria-live', 'polite');
    expect(live).toHaveTextContent('rock.png: Ready. empty.png: This file is empty.');
    expect(live?.textContent).not.toContain('..');
  });
});
