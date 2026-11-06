import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import {
  aDetail,
  anAsset,
  aVersion,
  countRequests,
  fakeApi,
  json,
  problem,
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

  it('moves focus to the heading when the detail replaces the list (compact)', async () => {
    fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [json(withVersions)],
    });

    renderApp(`/assets/${asset.id}`);

    expect(await screen.findByRole('heading', { name: 'rock_albedo' })).toHaveFocus();
    expect(screen.getByRole('link', { name: 'All assets' })).toHaveAttribute('href', '/assets');
  });

  it('keeps focus in place and marks the selected card when expanded', async () => {
    setViewportExpanded(true);
    fakeApi({
      [LIST]: [json({ items: [asset], next_cursor: null })],
      [DETAIL]: [json(withVersions)],
    });

    renderApp(`/assets/${asset.id}`);

    expect(await screen.findByRole('heading', { name: 'rock_albedo' })).not.toHaveFocus();
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
});
