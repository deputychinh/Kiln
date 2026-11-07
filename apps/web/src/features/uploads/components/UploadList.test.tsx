import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { type ReactElement, useState } from 'react';

import { UploadStatus } from '@/enums/upload-status.enum';
import { UploadList } from '@/features/uploads/components/UploadList';
import type { UploadItem, UploadsApi, UploadTarget } from '@/interfaces/upload.interface';
import { anItem, uploadsWith } from '@/test/upload-items';

const focusUploadButton = (): HTMLElement | null => document.getElementById('upload');

/** The list beside the button that adds files, inside a router (a ready row links to its asset). */
const renderInRouter = (list: ReactElement) => {
  const router = createRouter({
    routeTree: createRootRoute({
      component: () => (
        <>
          <button id="upload" type="button">
            Upload
          </button>
          {list}
        </>
      ),
    }),
    history: createMemoryHistory({ initialEntries: ['/assets'] }),
  });
  render(<RouterProvider router={router} />);
};

const renderList = (uploads: UploadsApi, target?: UploadTarget, listLabel = 'Uploads') =>
  renderInRouter(
    <UploadList
      uploads={uploads}
      target={target}
      listLabel={listLabel}
      fallbackFocus={focusUploadButton}
    />,
  );

/** The list over a tiny in-memory queue, so Cancel, Retry and Remove change the rows. */
const StatefulList = ({ initial }: { initial: UploadItem[] }) => {
  const [items, setItems] = useState(initial);
  const set = (id: string, status: UploadStatus) =>
    setItems((rows) => rows.map((row) => (row.id === id ? { ...row, status } : row)));
  return (
    <UploadList
      uploads={{
        ...uploadsWith(items),
        cancel: (id) => set(id, UploadStatus.Cancelled),
        retry: (id) => set(id, UploadStatus.Queued),
        remove: (id) => setItems((rows) => rows.filter((row) => row.id !== id)),
      }}
      listLabel="Uploads"
      fallbackFocus={focusUploadButton}
    />
  );
};

describe('UploadList', () => {
  it('shows nothing while it has no rows of its own', async () => {
    renderList(uploadsWith([anItem({ targetAssetId: 'asset-9' })]));

    await screen.findByRole('button', { name: 'Upload' });
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
  });

  it('shows only the versions of its asset, with their summary', async () => {
    const target = { assetId: 'asset-9', kind: 'model' } as const;
    renderList(
      uploadsWith([
        anItem({ id: 'mine', file: new File(['x'], 'crate_v2.glb'), targetAssetId: 'asset-9' }),
        anItem({ id: 'gallery', file: new File(['x'], 'rock.png') }),
        anItem({ id: 'other', file: new File(['x'], 'tree_v4.glb'), targetAssetId: 'asset-3' }),
      ]),
      target,
      'New versions of crate',
    );

    const list = await screen.findByRole('list', { name: 'New versions of crate' });
    expect(
      within(list)
        .getAllByRole('listitem')
        .map((row) => row.textContent),
    ).toEqual([expect.stringContaining('crate_v2.glb')]);
    expect(screen.getByText('0 of 1 uploaded')).toBeVisible();
  });

  it('shows a running upload with its percent, a named progress bar and a named Cancel', async () => {
    const uploads = uploadsWith([anItem({ status: UploadStatus.Uploading, progress: 42.4 })]);
    renderList(uploads);

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
    renderList(uploads);

    expect(await screen.findByText('Storage refused the file. Try again.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Retry rock.png' }));
    await userEvent.click(screen.getByRole('button', { name: 'Remove rock.png' }));
    expect(uploads.retry).toHaveBeenCalledWith('row-1');
    expect(uploads.remove).toHaveBeenCalledWith('row-1');
  });

  it('offers only Remove when retrying cannot help', async () => {
    renderList(
      uploadsWith([
        anItem({ status: UploadStatus.Failed, error: 'This file is empty.', canRetry: false }),
      ]),
    );

    expect(await screen.findByRole('button', { name: 'Remove rock.png' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Retry/ })).not.toBeInTheDocument();
  });

  it('counts failed files in the summary, and can leave the summary to its container', async () => {
    const items = [
      anItem({ status: UploadStatus.Ready }),
      anItem({ id: 'row-2', status: UploadStatus.Failed, error: 'x' }),
    ];
    renderList(uploadsWith(items));
    expect(await screen.findByText('1 of 2 uploaded, 1 failed')).toBeInTheDocument();
  });

  it('hides its summary when the container shows it', async () => {
    renderInRouter(
      <UploadList
        uploads={uploadsWith([anItem({ status: UploadStatus.Ready })])}
        listLabel="Uploads"
        hasSummary={false}
        fallbackFocus={focusUploadButton}
      />,
    );

    await screen.findByRole('list', { name: 'Uploads' });
    expect(screen.queryByText('1 of 1 uploaded')).not.toBeInTheDocument();
  });

  it('explains the empty asset a cancelled upload leaves behind', async () => {
    renderList(uploadsWith([anItem({ status: UploadStatus.Cancelled, assetId: 'asset-1' })]));

    expect(
      await screen.findByText('Cancelled. The empty asset it started is removed within 24 hours.'),
    ).toBeInTheDocument();
  });

  it('keeps keyboard focus in the row when Cancel turns into Retry, and Retry into Cancel', async () => {
    renderInRouter(<StatefulList initial={[anItem({ status: UploadStatus.Uploading })]} />);

    await userEvent.click(await screen.findByRole('button', { name: 'Cancel rock.png' }));
    expect(await screen.findByRole('button', { name: 'Retry rock.png' })).toHaveFocus();

    await userEvent.click(screen.getByRole('button', { name: 'Retry rock.png' }));
    expect(await screen.findByRole('button', { name: 'Cancel rock.png' })).toHaveFocus();
  });

  it('moves focus to the next row after Remove, or to the button that adds files when empty', async () => {
    renderInRouter(
      <StatefulList
        initial={[
          anItem({ status: UploadStatus.Failed, error: 'x' }),
          anItem({
            id: 'row-2',
            status: UploadStatus.Failed,
            error: 'y',
            file: new File(['x'], 'tree.png'),
          }),
        ]}
      />,
    );

    await userEvent.click(await screen.findByRole('button', { name: 'Remove rock.png' }));
    expect(await screen.findByRole('button', { name: 'Retry tree.png' })).toHaveFocus();

    await userEvent.click(screen.getByRole('button', { name: 'Remove tree.png' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Upload' })).toHaveFocus());
  });

  it('lets a cancelled upload be retried', async () => {
    renderList(uploadsWith([anItem({ status: UploadStatus.Cancelled })]));

    expect(await screen.findByRole('button', { name: 'Retry rock.png' })).toBeInTheDocument();
    expect(screen.getByText('Cancelled')).toBeInTheDocument();
  });

  it('shows processing with a full bar and lets the row be dismissed', async () => {
    renderList(uploadsWith([anItem({ status: UploadStatus.Processing, progress: 100 })]));

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
    renderList(uploadsWith([anItem({ status: UploadStatus.Ready, assetId: 'asset-1' })]));

    expect(await screen.findByRole('link', { name: 'rock.png' })).toHaveAttribute(
      'href',
      '/assets/asset-1',
    );
    expect(screen.getByText('1 of 1 uploaded')).toBeInTheDocument();
  });
});
