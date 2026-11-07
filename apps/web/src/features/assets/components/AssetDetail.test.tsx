import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import {
  aDetail,
  anAsset,
  aVersion,
  countRequests,
  fakeApi,
  json,
  problem,
  signedUrl,
  urlOf,
} from '@/test/fake-api';
import { fileInputOf } from '@/test/file-input';
import { renderApp } from '@/test/render-app';
import { setViewportExpanded, setViewportLarge } from '@/test/viewport';

const LIST = '/api/v1/assets?limit=24';
const asset = anAsset();
const DETAIL = `/api/v1/assets/${asset.id}`;

const withVersions = aDetail({
  versions: [
    aVersion(),
    aVersion({
      id: 'v2',
      number: 2,
      status: 'failed',
      failure_reason: 'IMAGE_TOO_LARGE',
      file_name: 'rock_albedo_8k.png',
      size_bytes: 480_000_000,
      thumbnail_url: null,
    }),
  ],
});

describe('AssetDetail', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('shows the facts and the versions newest first with text statuses', async () => {
    fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [json(withVersions)],
    });

    renderApp(`/assets/${asset.id}`);

    const detail = await screen.findByRole('article', { name: 'rock_albedo' });
    expect(within(detail).getByRole('img', { name: 'Preview of rock_albedo' })).toHaveAttribute(
      'loading',
      'eager',
    );
    const versions = within(detail).getAllByRole('listitem');
    expect(versions[0]).toHaveTextContent('Version 2');
    expect(versions[0]).toHaveTextContent('Failed');
    expect(versions[0]).toHaveTextContent('rock_albedo_8k.png · 480 MB');
    expect(versions[0]).toHaveTextContent('The image has too many pixels to preview.');
    expect(versions[1]).toHaveTextContent('Version 1');
    expect(versions[1]).toHaveTextContent('Ready');
    expect(versions[1]).toHaveTextContent('1.5 MB');
  });

  it('offers Upload new version for the asset and refuses a file of the other kind before sending', async () => {
    const fetchMock = fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [json(withVersions)],
    });
    renderApp(`/assets/${asset.id}`);

    const detail = await screen.findByRole('article', { name: 'rock_albedo' });
    const button = within(detail).getByRole('button', {
      name: 'Upload new version of rock_albedo',
    });
    expect(button).toHaveTextContent('Upload new version');
    const input = fileInputOf(button);
    expect(input.accept).toBe('image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp');

    await userEvent.upload(input, new File(['glb'], 'crate.glb'), { applyAccept: false });

    const rows = within(detail).getByRole('list', { name: 'New versions of rock_albedo' });
    expect(rows).toHaveTextContent('This asset holds images: choose a PNG, JPEG or WebP file.');
    expect(within(rows).queryByRole('button', { name: /Retry/ })).not.toBeInTheDocument();
    expect(countRequests(fetchMock, `${DETAIL}/versions`)).toBe(0);
  });

  it('has one upload live region and one stray-drop guard for the page, with gallery and detail open', async () => {
    setViewportExpanded(true);
    fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [json(withVersions)],
    });
    renderApp(`/assets/${asset.id}`);
    await screen.findByRole('article', { name: 'rock_albedo' });
    await screen.findByRole('list', { name: 'Assets' });

    // The upload region is portalled onto <body>; the gallery's own "N shown" status is not.
    expect(document.body.querySelectorAll(':scope > [aria-live="polite"]')).toHaveLength(1);
    const drop = new Event('drop', { bubbles: true, cancelable: true });
    Object.defineProperty(drop, 'dataTransfer', {
      value: { types: ['Files'], dropEffect: 'copy' },
    });
    document.body.dispatchEvent(drop);
    expect(drop.defaultPrevented).toBe(true);
  });

  it('refuses an empty new version with the gallery wording', async () => {
    const fetchMock = fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [json(withVersions)],
    });
    renderApp(`/assets/${asset.id}`);
    const detail = await screen.findByRole('article', { name: 'rock_albedo' });
    const input = fileInputOf(
      within(detail).getByRole('button', { name: 'Upload new version of rock_albedo' }),
    );

    await userEvent.upload(input, new File([], 'rock_v2.png', { type: 'image/png' }));

    expect(
      within(detail).getByRole('list', { name: 'New versions of rock_albedo' }),
    ).toHaveTextContent('This file is empty.');
    expect(countRequests(fetchMock, `${DETAIL}/versions`)).toBe(0);
  });

  it('offers Compare versions only when there are two versions or more', async () => {
    fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [json(withVersions)],
    });
    renderApp(`/assets/${asset.id}`);

    const link = await screen.findByRole('link', { name: 'Compare versions' });
    expect(link).toHaveAttribute('href', `/assets/${asset.id}/compare`);
    expect(link).toHaveTextContent('Compare');
  });

  it('offers no comparison for an asset with one version', async () => {
    fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [json(aDetail())],
    });
    renderApp(`/assets/${asset.id}`);

    await screen.findByRole('article', { name: 'rock_albedo' });
    expect(screen.queryByRole('link', { name: 'Compare versions' })).not.toBeInTheDocument();
  });

  it('offers View in 3D only on the ready versions of a model', async () => {
    const glb = { content_type: 'model/gltf-binary', file_name: 'crate.glb' };
    fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [
        json(
          aDetail({
            kind: 'model',
            versions: [
              aVersion({ ...glb, download_url: 'http://s3.test/kiln/m1.glb?sig=1' }),
              aVersion({ ...glb, id: 'v2', number: 2, status: 'failed', download_url: null }),
              aVersion({ ...glb, id: 'v3', number: 3, status: 'processing', download_url: null }),
            ],
          }),
        ),
      ],
    });
    renderApp(`/assets/${asset.id}`);

    // The header's action opens the newest ready version; each ready version has its own link.
    const links = await screen.findAllByRole('link', { name: 'View version 1 in 3D' });
    expect(links).toHaveLength(2);
    for (const link of links) {
      expect(link).toHaveAttribute('href', `/assets/${asset.id}/view?version=1`);
      expect(link).toHaveTextContent('View in 3D');
    }
    expect(screen.getAllByRole('link', { name: /in 3D/ })).toHaveLength(2);
  });

  it('offers no 3D view for an image', async () => {
    fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [json(aDetail({ versions: [aVersion({ download_url: 'http://s3.test/a.png' })] }))],
    });
    renderApp(`/assets/${asset.id}`);

    await screen.findByRole('article', { name: 'rock_albedo' });
    expect(screen.queryByRole('link', { name: /in 3D/ })).not.toBeInTheDocument();
  });

  it('makes the asset name the page heading when the detail replaces the list (compact)', async () => {
    fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [json(withVersions)],
    });

    renderApp(`/assets/${asset.id}`);

    const heading = await screen.findByRole('heading', { name: 'rock_albedo' });
    expect(heading).toHaveFocus();
    expect(heading.tagName).toBe('H1');
    expect(screen.getByRole('link', { name: 'All assets' })).toHaveAttribute('href', '/assets');
  });

  it('keeps focus in place and marks the selected card when expanded', async () => {
    setViewportExpanded(true);
    fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [json(withVersions)],
    });

    renderApp(`/assets/${asset.id}`);

    const heading = await screen.findByRole('heading', { name: 'rock_albedo' });
    expect(heading).not.toHaveFocus();
    expect(heading.tagName).toBe('H2');
    const card = await screen.findByRole('link', { name: /rock_albedo/ });
    expect(card).toHaveAttribute('aria-current', 'page');
  });

  it('asks to select an asset when none is selected', async () => {
    fakeApi({ [LIST]: [json({ items: [asset], next_cursor: null })] });

    renderApp('/assets');

    expect(await screen.findByText('Select an asset to see its versions.')).toBeInTheDocument();
  });

  it.each([
    [404, 'Asset not found', 'ASSET_NOT_FOUND'],
    [422, 'Validation failed', 'VALIDATION_FAILED'],
  ])('shows "not found" without retrying on %i', async (status, title, code) => {
    const fetchMock = fakeApi({
      [LIST]: [json({ items: [], next_cursor: null })],
      '/api/v1/assets/': [problem(status, title, code)],
    });

    renderApp('/assets/nope');

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Asset not found');
    expect(within(alert).queryByRole('button')).not.toBeInTheDocument();
    expect(within(alert).getByRole('link', { name: 'All assets' })).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([url]) => urlOf(url).includes('/nope'))).toHaveLength(1);
  });

  it('offers a retry when loading fails for another reason', async () => {
    fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [
        problem(503, 'Database unavailable', 'DATABASE_UNAVAILABLE'),
        problem(503, 'Database unavailable', 'DATABASE_UNAVAILABLE'),
        problem(503, 'Database unavailable', 'DATABASE_UNAVAILABLE'),
        json(withVersions),
      ],
    });

    renderApp(`/assets/${asset.id}`);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Could not load this asset');
    expect(alert).toHaveTextContent('Database unavailable');
    await userEvent.click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('article', { name: 'rock_albedo' })).toBeInTheDocument();
  });

  it('refreshes while a version is processing until it is ready', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const processing = aDetail({
      thumbnail_url: null,
      versions: [aVersion({ status: 'processing', thumbnail_url: null })],
    });
    const fetchMock = fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [json(processing), json(aDetail())],
    });

    renderApp(`/assets/${asset.id}`);
    const detail = await screen.findByRole('article', { name: 'rock_albedo' });
    expect(within(detail).getByText('Processing')).toBeInTheDocument();

    await vi.advanceTimersByTimeAsync(3_000);

    expect(await within(detail).findByText('Ready')).toBeInTheDocument();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(countRequests(fetchMock, DETAIL)).toBe(2);
  });

  it('shows the kind placeholder when there is no preview yet', async () => {
    fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [json(aDetail({ kind: 'model', thumbnail_url: null }))],
    });

    renderApp(`/assets/${asset.id}`);

    const detail = await screen.findByRole('article', { name: 'rock_albedo' });
    expect(within(detail).queryByRole('img')).not.toBeInTheDocument();
    await waitFor(() => expect(within(detail).getAllByText('Model').length).toBeGreaterThan(0));
  });

  it('keeps the hero image URL while polling re-signs the same preview', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true, now: Date.parse('2026-11-06T12:00:00Z') });
    const cover = (signedAt: string) => signedUrl(`thumbs/${asset.id}/v1.webp`, signedAt);
    const polling = (signedAt: string) =>
      aDetail({
        thumbnail_url: cover(signedAt),
        versions: [
          aVersion({ thumbnail_url: cover(signedAt) }),
          aVersion({ id: 'v2', number: 2, status: 'processing', thumbnail_url: null }),
        ],
      });
    const fetchMock = fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [json(polling('20261106T120000Z')), json(polling('20261106T120003Z'))],
    });

    renderApp(`/assets/${asset.id}`);
    const image = await screen.findByRole('img', { name: 'Preview of rock_albedo' });
    await vi.advanceTimersByTimeAsync(3_000);
    await waitFor(() => expect(countRequests(fetchMock, DETAIL)).toBeGreaterThanOrEqual(2));

    expect(screen.getByRole('img', { name: 'Preview of rock_albedo' })).toBe(image);
    expect(image).toHaveAttribute('src', cover('20261106T120000Z'));
  });

  it('refreshes the gallery once processing ends, so the card gets its preview', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchMock = fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [
        json(aDetail({ versions: [aVersion({ status: 'processing', thumbnail_url: null })] })),
        json(aDetail()),
      ],
    });

    renderApp(`/assets/${asset.id}`);
    await screen.findByRole('article', { name: 'rock_albedo' });
    expect(countRequests(fetchMock, LIST)).toBe(1);

    await vi.advanceTimersByTimeAsync(3_000);

    await waitFor(() => expect(countRequests(fetchMock, LIST)).toBe(2));
  });

  it('says when a refresh failed and the detail may be out of date', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const down = problem(503, 'Database unavailable', 'DATABASE_UNAVAILABLE');
    fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [
        json(aDetail({ versions: [aVersion({ status: 'processing', thumbnail_url: null })] })),
        down,
      ],
    });

    renderApp(`/assets/${asset.id}`);
    const detail = await screen.findByRole('article', { name: 'rock_albedo' });
    await vi.advanceTimersByTimeAsync(3_000);

    expect(await within(detail).findByRole('status')).toHaveTextContent(
      'Could not refresh, so this may be out of date.',
    );
    expect(within(detail).getByText('Processing')).toBeInTheDocument();
  });

  it('returns focus to the card it came from when going back (compact)', async () => {
    fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [json(withVersions)],
    });

    renderApp(`/assets/${asset.id}`);
    await userEvent.click(await screen.findByRole('link', { name: 'All assets' }));

    await waitFor(() => expect(screen.getByRole('link', { name: /rock_albedo/ })).toHaveFocus());
  });

  it('shows the fresh preview after the hero image failed to load once', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true, now: Date.parse('2026-11-06T12:00:00Z') });
    const cover = (signedAt: string) => signedUrl(`thumbs/${asset.id}/v1.webp`, signedAt);
    const fetchMock = fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [
        json(aDetail({ thumbnail_url: cover('20261106T120000Z') })),
        json(aDetail({ thumbnail_url: cover('20261106T120005Z') })),
      ],
    });

    renderApp(`/assets/${asset.id}`);
    fireEvent.error(await screen.findByRole('img', { name: 'Preview of rock_albedo' }));

    await waitFor(() =>
      expect(screen.getByRole('img', { name: 'Preview of rock_albedo' })).toHaveAttribute(
        'src',
        cover('20261106T120005Z'),
      ),
    );
    // The object itself is broken: failing again does not start another refresh (no loop).
    fireEvent.error(screen.getByRole('img', { name: 'Preview of rock_albedo' }));
    await vi.advanceTimersByTimeAsync(100);
    expect(countRequests(fetchMock, DETAIL)).toBe(2);
  });

  it('focuses the detail pane on compact screens while loading or when not found', async () => {
    fakeApi({
      [LIST]: [json({ items: [], next_cursor: null })],
      '/api/v1/assets/': [problem(404, 'Asset not found', 'ASSET_NOT_FOUND')],
    });

    renderApp('/assets/nope');

    await screen.findByRole('alert');
    expect(document.activeElement).toHaveClass('asset-detail__pane');
    expect(screen.getByRole('heading', { level: 1, name: 'Asset not found' })).toBeInTheDocument();
  });

  it('focuses the heading, not the pane, when a cached asset opens again (compact)', async () => {
    fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [json(withVersions)],
    });

    renderApp(`/assets/${asset.id}`);
    await userEvent.click(await screen.findByRole('link', { name: 'All assets' }));
    await userEvent.click(await screen.findByRole('link', { name: /rock_albedo/ }));

    expect(await screen.findByRole('heading', { name: 'rock_albedo' })).toHaveFocus();
  });

  it('explains a model that cannot be previewed', async () => {
    fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [
        json(
          aDetail({
            kind: 'model',
            thumbnail_url: null,
            versions: [
              aVersion({
                status: 'failed',
                failure_reason: 'UNREADABLE_MODEL',
                thumbnail_url: null,
              }),
            ],
          }),
        ),
      ],
    });

    renderApp(`/assets/${asset.id}`);

    const detail = await screen.findByRole('article', { name: 'rock_albedo' });
    expect(detail).toHaveTextContent('Compressed meshes (Draco, meshopt)');
  });

  it('explains an upload that was never completed', async () => {
    fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [
        json(
          aDetail({
            thumbnail_url: null,
            versions: [
              aVersion({ status: 'failed', failure_reason: 'UPLOAD_EXPIRED', thumbnail_url: null }),
            ],
          }),
        ),
      ],
    });

    renderApp(`/assets/${asset.id}`);

    const detail = await screen.findByRole('article', { name: 'rock_albedo' });
    expect(detail).toHaveTextContent('The upload was never completed. Upload the file again.');
  });

  it('shows the versions tab with its count, and the facts on the Info tab', async () => {
    fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [json(withVersions)],
    });
    renderApp(`/assets/${asset.id}`);
    const detail = await screen.findByRole('article', { name: 'rock_albedo' });

    const versionsTab = within(detail).getByRole('tab', { name: 'Versions 2' });
    expect(versionsTab).toHaveAttribute('aria-selected', 'true');
    expect(within(detail).getByText('Image', { selector: '.badge' })).toBeInTheDocument();
    await userEvent.click(within(detail).getByRole('tab', { name: 'Info' }));

    const info = within(detail).getByRole('tabpanel', { name: 'Info' });
    expect(info).toHaveTextContent('KindImage');
    expect(info).toHaveTextContent('Versions2');
    expect(info).toHaveTextContent('Latest filerock_albedo_8k.png · 480 MB');
    expect(within(detail).queryByRole('tabpanel', { name: 'Versions 2' })).not.toBeInTheDocument();
  });

  it('keeps the gallery view options on the way back', async () => {
    fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [json(withVersions)],
    });

    renderApp(`/assets/${asset.id}?kind=image&size=small`);

    expect(await screen.findByRole('link', { name: 'All assets' })).toHaveAttribute(
      'href',
      '/assets?kind=image&size=small',
    );
  });

  it.each([
    {
      name: 'an expanded window with nothing selected',
      isLarge: false,
      items: [asset],
      isHidden: true,
    },
    {
      name: 'a large window with nothing selected',
      isLarge: true,
      items: [asset],
      isHidden: false,
    },
    { name: 'a large window and no assets at all', isLarge: true, items: [], isHidden: true },
  ])('gives the grid the full width on $name: $isHidden', async ({ isLarge, items, isHidden }) => {
    if (isLarge) setViewportLarge(true);
    else setViewportExpanded(true);
    fakeApi({ [LIST]: [json({ items, next_cursor: null })] });

    renderApp('/assets');

    await screen.findByRole('heading', { level: 1, name: 'Assets' });
    await waitFor(() =>
      expect(
        document.querySelector('.list-detail')?.classList.contains('list-detail--single'),
      ).toBe(isHidden),
    );
  });
});
