import { act, createEvent, fireEvent, screen, within } from '@testing-library/react';

import { aDetail, anAsset, countRequests, fakeApi, json } from '@/test/fake-api';
import { renderApp } from '@/test/render-app';

const LIST = '/api/v1/assets?limit=24';
const asset = anAsset();
const DETAIL = `/api/v1/assets/${asset.id}`;

/** Files dragged over the window, as the browser reports them before the drop. */
const dragFilesOverWindow = () => {
  const enter = new Event('dragenter', { bubbles: true, cancelable: true });
  Object.defineProperty(enter, 'dataTransfer', { value: { types: ['Files'], files: [] } });
  act(() => {
    window.dispatchEvent(enter);
  });
};

const dropOn = (targetId: string, files: File[]) => {
  const target = document.querySelector(`[data-drop-target="${targetId}"]`);
  if (!target) throw new Error(`No drop target ${targetId}`);
  const drop = createEvent.drop(target);
  Object.defineProperty(drop, 'dataTransfer', { value: { types: ['Files'], files } });
  fireEvent(target, drop);
  return drop;
};

describe('UploadDropOverlay', () => {
  afterEach(() => vi.restoreAllMocks());

  it('takes files dropped anywhere on the gallery as new assets', async () => {
    fakeApi({ [LIST]: [json({ items: [asset], next_cursor: null })] });
    renderApp('/assets');
    await screen.findByRole('list', { name: 'Assets' });

    dragFilesOverWindow();
    const overlay = document.querySelector('.drop-overlay');
    expect(overlay).toHaveTextContent('Drop files to upload');
    expect(overlay).toHaveTextContent('New assets');
    expect(overlay).not.toHaveTextContent('New version of');
    const drop = dropOn('assets', [new File(['x'], 'notes.txt', { type: 'text/plain' })]);

    expect(drop.defaultPrevented).toBe(true);
    const rows = await screen.findByRole('list', { name: 'Uploads' });
    expect(within(rows).getByText('notes.txt')).toBeInTheDocument();
    expect(document.querySelector('.drop-overlay')).not.toBeInTheDocument();
  });

  it('also offers the open asset as a target, and adds dropped files as its versions', async () => {
    const fetchMock = fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [json(aDetail())],
    });
    renderApp(`/assets/${asset.id}`);
    await screen.findByRole('article', { name: 'rock_albedo' });

    dragFilesOverWindow();
    expect(document.querySelector('.drop-overlay')).toHaveTextContent('New version of rock_albedo');
    dropOn('version', [new File(['glb'], 'crate.glb')]);

    expect(
      await screen.findByRole('list', { name: 'New versions of rock_albedo' }),
    ).toHaveTextContent('This asset holds images: choose a PNG, JPEG or WebP file.');
    expect(countRequests(fetchMock, `${DETAIL}/versions`)).toBe(0);
  });
});
