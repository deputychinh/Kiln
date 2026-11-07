import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { anAsset, fakeApi, json } from '@/test/fake-api';
import { fileInputOf } from '@/test/file-input';
import { renderApp } from '@/test/render-app';

const LIST = '/api/v1/assets?limit=24';
const text = (name: string): File => new File(['x'], name, { type: 'text/plain' });

/** The gallery with its top bar; files refused before sending need no upload API. */
const renderGallery = async () => {
  fakeApi({ [LIST]: [json({ items: [anAsset()], next_cursor: null })] });
  renderApp('/assets');
  await screen.findByRole('list', { name: 'Assets' });
  const upload = within(screen.getByRole('banner')).getByRole('button', { name: 'Upload' });
  const add = (...files: File[]) =>
    userEvent.upload(fileInputOf(upload), files, { applyAccept: false });
  return { upload, add };
};

const tray = (): HTMLElement | null => screen.queryByRole('region', { name: 'Uploads' });

describe('UploadTray', () => {
  afterEach(() => vi.restoreAllMocks());

  it('stays hidden until files are added, then lists them with a summary', async () => {
    const { add } = await renderGallery();
    expect(tray()).not.toBeInTheDocument();

    await add(text('notes.txt'), text('readme.txt'));

    const region = await screen.findByRole('region', { name: 'Uploads' });
    expect(within(region).getByText('0 of 2 uploaded, 2 failed')).toBeInTheDocument();
    expect(within(region).getAllByRole('listitem')).toHaveLength(2);
  });

  it('collapses to its summary and opens again when more files are added', async () => {
    const { add } = await renderGallery();
    await add(text('notes.txt'));
    const region = await screen.findByRole('region', { name: 'Uploads' });

    const collapse = within(region).getByRole('button', { name: 'Collapse uploads' });
    expect(collapse).toHaveAttribute('aria-expanded', 'true');
    await userEvent.click(collapse);

    const expand = within(region).getByRole('button', { name: 'Expand uploads' });
    expect(expand).toHaveAttribute('aria-expanded', 'false');
    expect(within(region).queryByRole('list')).not.toBeInTheDocument();
    expect(within(region).getByText('0 of 1 uploaded, 1 failed')).toBeVisible();

    await add(text('readme.txt'));
    expect(within(region).getByRole('list', { name: 'Uploads' })).toBeVisible();
    expect(within(region).getByRole('button', { name: 'Collapse uploads' })).toBeInTheDocument();
  });

  it('can be expanded again by hand', async () => {
    const { add } = await renderGallery();
    await add(text('notes.txt'));
    const region = await screen.findByRole('region', { name: 'Uploads' });

    await userEvent.click(within(region).getByRole('button', { name: 'Collapse uploads' }));
    await userEvent.click(within(region).getByRole('button', { name: 'Expand uploads' }));

    expect(within(region).getByRole('list', { name: 'Uploads' })).toBeVisible();
  });

  it('hides once the last row is removed and gives focus back to Upload', async () => {
    const { add, upload } = await renderGallery();
    await add(text('notes.txt'));

    await userEvent.click(await screen.findByRole('button', { name: 'Remove notes.txt' }));

    await waitFor(() => expect(upload).toHaveFocus());
    expect(tray()).not.toBeInTheDocument();
  });
});
