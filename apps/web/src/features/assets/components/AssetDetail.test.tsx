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
import { renderApp } from '@/test/render-app';
import { setViewportExpanded } from '@/test/viewport';

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

  it('offers a version zone for the asset and refuses a file of the other kind before sending', async () => {
    const fetchMock = fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [json(withVersions)],
    });
    renderApp(`/assets/${asset.id}`);

    const detail = await screen.findByRole('article', { name: 'rock_albedo' });
    const zone = within(detail).getByRole('group', {
      name: 'Drop a new version of rock_albedo here',
    });
    const input = zone.querySelector<HTMLInputElement>('input[type="file"]')!;
    expect(input.accept).toBe('image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp');
    expect(within(zone).getByRole('button', { name: 'Choose a file' })).toBeVisible();

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
    await screen.findByRole('group', { name: 'Drop images or .glb files here' });

    // The upload region is portalled onto <body>; the gallery's own "N shown" status is not.
    expect(document.body.querySelectorAll(':scope > [aria-live="polite"]')).toHaveLength(1);
    const drop = new Event('drop', { bubbles: true, cancelable: true });
    Object.defineProperty(drop, 'dataTransfer', {
      value: { types: ['Files'], dropEffect: 'copy' },
    });
    document.body.dispatchEvent(drop);
    expect(drop.defaultPrevented).toBe(true);
  });

  it('refuses an empty file in the version zone with the gallery wording', async () => {
    const fetchMock = fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [json(withVersions)],
    });
    renderApp(`/assets/${asset.id}`);
    const detail = await screen.findByRole('article', { name: 'rock_albedo' });
    const input = within(detail)
      .getByRole('group', { name: 'Drop a new version of rock_albedo here' })
      .querySelector<HTMLInputElement>('input[type="file"]')!;

    await userEvent.upload(input, new File([], 'rock_v2.png', { type: 'image/png' }));

    expect(
      within(detail).getByRole('list', { name: 'New versions of rock_albedo' }),
    ).toHaveTextContent('This file is empty.');
    expect(countRequests(fetchMock, `${DETAIL}/versions`)).toBe(0);
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
});
