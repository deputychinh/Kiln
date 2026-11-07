import { focusManager } from '@tanstack/react-query';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { anAsset, countRequests, fakeApi, json, problem, urlOf } from '@/test/fake-api';
import { fileInputOf } from '@/test/file-input';
import { renderApp } from '@/test/render-app';

const LIST = '/api/v1/assets?limit=24';
const PAGE_2 = '/api/v1/assets?limit=24&cursor=c1';

const rock = anAsset();
const tree = anAsset({
  id: '0190f1c2-0000-7000-8000-000000000002',
  name: 'tree_oak',
  kind: 'model',
  thumbnail_url: null,
});

describe('AssetGallery', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('redirects / to /assets', async () => {
    fakeApi({ [LIST]: [json({ items: [], next_cursor: null })] });

    const { router } = renderApp('/');

    await waitFor(() => expect(router.state.location.pathname).toBe('/assets'));
  });

  it('announces loading once, then shows a card per asset newest first', async () => {
    fakeApi({ [LIST]: [json({ items: [rock, tree], next_cursor: null })] });

    renderApp('/assets');

    expect(await screen.findByRole('status')).toHaveTextContent('Loading assets…');
    const list = await screen.findByRole('list', { name: 'Assets' });
    const links = within(list).getAllByRole('link');
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      `/assets/${rock.id}`,
      `/assets/${tree.id}`,
    ]);
    expect(links[0]).toHaveTextContent('rock_albedo');
    expect(links[0]).toHaveTextContent('Image');
    expect(links[1]).toHaveTextContent('Model');
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument();
    expect(screen.getByText('Showing 2 assets')).toBeInTheDocument();
  });

  it('shows the preview image without alt text (the card names it) or a kind placeholder', async () => {
    fakeApi({ [LIST]: [json({ items: [rock, tree], next_cursor: null })] });

    renderApp('/assets');

    const list = await screen.findByRole('list', { name: 'Assets' });
    const [rockImage] = within(list).getAllByRole('presentation');
    expect(rockImage).toHaveAttribute('src', rock.thumbnail_url);
    expect(list.querySelectorAll('img')).toHaveLength(1);
  });

  it('says what to do when there are no assets, with an Upload button', async () => {
    fakeApi({ [LIST]: [json({ items: [], next_cursor: null })] });

    renderApp('/assets');

    expect(await screen.findByRole('heading', { name: 'No assets yet' })).toBeInTheDocument();
    expect(screen.getByText(/drop files anywhere on this page/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Upload files' })).toBeInTheDocument();
  });

  it('shows card placeholders while the first page loads, and Upload stays in the top bar', async () => {
    vi.spyOn(globalThis, 'fetch').mockReturnValue(new Promise(() => undefined));

    renderApp('/assets');

    const status = await screen.findByRole('status');
    expect(status).toHaveTextContent('Loading assets…');
    expect(status.querySelectorAll('.skeleton--card')).toHaveLength(8);
    expect(
      within(screen.getByRole('banner')).getByRole('button', { name: 'Upload' }),
    ).toBeInTheDocument();
  });

  it('keeps the upload list when the gallery goes from empty to a list', async () => {
    fakeApi({
      [LIST]: [json({ items: [], next_cursor: null }), json({ items: [rock], next_cursor: null })],
    });
    const { queryClient } = renderApp('/assets');
    await screen.findByRole('heading', { name: 'No assets yet' });
    const input = fileInputOf(
      within(screen.getByRole('banner')).getByRole('button', { name: 'Upload' }),
    );

    await userEvent.upload(input, new File(['x'], 'notes.txt', { type: 'text/plain' }), {
      applyAccept: false,
    });
    expect(
      await screen.findByText('Only PNG, JPEG, WebP and .glb files can be uploaded.'),
    ).toBeInTheDocument();

    await queryClient.invalidateQueries();
    expect(await screen.findByRole('list', { name: 'Assets' })).toBeInTheDocument();
    expect(
      within(screen.getByRole('list', { name: 'Uploads' })).getByText('notes.txt'),
    ).toBeInTheDocument();
  });

  it('shows the problem title with a retry that fetches again', async () => {
    const fetchMock = fakeApi({
      [LIST]: [
        problem(503, 'Storage is unavailable', 'STORAGE_UNAVAILABLE'),
        problem(503, 'Storage is unavailable', 'STORAGE_UNAVAILABLE'),
        problem(503, 'Storage is unavailable', 'STORAGE_UNAVAILABLE'),
        json({ items: [rock], next_cursor: null }),
      ],
    });

    renderApp('/assets');

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Could not load assets');
    expect(alert).toHaveTextContent('Storage is unavailable');
    expect(countRequests(fetchMock, LIST)).toBe(3); // first try + 2 retries for a 5xx

    await userEvent.click(within(alert).getByRole('button', { name: 'Try again' }));

    expect(await screen.findByRole('link', { name: /rock_albedo/ })).toBeInTheDocument();
  });

  it('explains an unreachable API in plain words', async () => {
    fakeApi({ [LIST]: [new TypeError('Failed to fetch')] });

    renderApp('/assets');

    expect(await screen.findByRole('alert', {}, { timeout: 3000 })).toHaveTextContent(
      'Kiln cannot reach its server',
    );
  });

  it('loads the next page with the cursor and appends it', async () => {
    const fetchMock = fakeApi({
      [LIST]: [json({ items: [rock], next_cursor: 'c1' })],
      [PAGE_2]: [json({ items: [tree], next_cursor: null })],
    });

    renderApp('/assets');

    await userEvent.click(await screen.findByRole('button', { name: 'Load more' }));

    // The button goes away on the last page; focus lands on the first new card, not the body.
    await waitFor(() => expect(screen.getByRole('link', { name: /tree_oak/ })).toHaveFocus());
    expect(screen.getByRole('link', { name: /rock_albedo/ })).toBeInTheDocument();
    expect(countRequests(fetchMock, PAGE_2)).toBe(1);
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument();
  });

  it('keeps the loaded cards when the next page fails, and retries it', async () => {
    fakeApi({
      [LIST]: [json({ items: [rock], next_cursor: 'c1' })],
      [PAGE_2]: [
        problem(500, 'Internal error', 'INTERNAL'),
        problem(500, 'Internal error', 'INTERNAL'),
        problem(500, 'Internal error', 'INTERNAL'),
        json({ items: [tree], next_cursor: null }),
      ],
    });

    renderApp('/assets');
    await userEvent.click(await screen.findByRole('button', { name: 'Load more' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Could not load more assets');
    await waitFor(() =>
      expect(within(alert).getByRole('button', { name: 'Try again' })).toHaveFocus(),
    );
    expect(screen.getByRole('link', { name: /rock_albedo/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument();

    await userEvent.click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('link', { name: /tree_oak/ })).toBeInTheDocument();
  });

  it('ignores presses on Load more while the next page is loading', async () => {
    let release: (response: Response) => void = () => undefined;
    const fetchMock = fakeApi({ [LIST]: [json({ items: [rock], next_cursor: 'c1' })] });
    fetchMock.mockImplementation((input) =>
      urlOf(input).endsWith(PAGE_2)
        ? new Promise((resolve) => {
            release = resolve;
          })
        : Promise.resolve(json({ items: [rock], next_cursor: 'c1' })),
    );

    renderApp('/assets');
    const button = await screen.findByRole('button', { name: 'Load more' });
    await userEvent.click(button);

    const busy = await screen.findByRole('button', { name: 'Loading more…' });
    expect(busy).toHaveAttribute('aria-disabled', 'true');
    expect(busy).toHaveFocus();
    await userEvent.click(busy);
    expect(countRequests(fetchMock, PAGE_2)).toBe(1);

    release(json({ items: [tree], next_cursor: null }));
    expect(await screen.findByRole('link', { name: /tree_oak/ })).toBeInTheDocument();
  });

  it('refreshes signed URLs once for the whole list however many previews fail, never in a loop', async () => {
    const tree2 = anAsset({
      id: '0190f1c2-0000-7000-8000-000000000003',
      name: 'tree_pine',
      thumbnail_url: 'http://s3.test/thumbs/pine.webp?sig=1',
    });
    const rock2 = anAsset({
      id: '0190f1c2-0000-7000-8000-000000000004',
      name: 'rock_moss',
      thumbnail_url: 'http://s3.test/thumbs/moss.webp?sig=1',
    });
    const resigned = [rock, tree2, rock2].map((asset) => ({
      ...asset,
      thumbnail_url: (asset.thumbnail_url ?? '').replace('sig=1', 'sig=2'),
    }));
    const fetchMock = fakeApi({
      [LIST]: [
        json({ items: [rock, tree2, rock2], next_cursor: null }),
        json({ items: resigned, next_cursor: null }),
      ],
    });

    renderApp('/assets');
    const list = await screen.findByRole('list', { name: 'Assets' });
    within(list)
      .getAllByRole('presentation')
      .forEach((image) => fireEvent.error(image));

    await waitFor(() =>
      expect(
        within(list)
          .getAllByRole('presentation')
          .map((image) => image.getAttribute('src')),
      ).toEqual(resigned.map((asset) => asset.thumbnail_url)),
    );
    expect(countRequests(fetchMock, LIST)).toBe(2);

    // The objects are broken: failing again shows placeholders and starts no further refresh.
    within(list)
      .getAllByRole('presentation')
      .forEach((image) => fireEvent.error(image));
    await waitFor(() => expect(within(list).queryByRole('presentation')).not.toBeInTheDocument());
    expect(countRequests(fetchMock, LIST)).toBe(2);
  });

  it('defers a preview refresh while the next page loads, then runs it once', async () => {
    let release: (response: Response) => void = () => undefined;
    const fetchMock = fakeApi({ [LIST]: [json({ items: [rock], next_cursor: 'c1' })] });
    fetchMock.mockImplementation((input) =>
      urlOf(input).endsWith(PAGE_2)
        ? new Promise((resolve) => {
            release = resolve;
          })
        : Promise.resolve(json({ items: [rock], next_cursor: 'c1' })),
    );

    renderApp('/assets');
    await userEvent.click(await screen.findByRole('button', { name: 'Load more' }));
    await screen.findByRole('button', { name: 'Loading more…' });
    fireEvent.error(screen.getByRole('presentation'));
    expect(countRequests(fetchMock, LIST)).toBe(1);

    release(json({ items: [tree], next_cursor: null }));

    await waitFor(() => expect(countRequests(fetchMock, LIST)).toBe(2));
  });

  it('does not refetch the list on window focus while it is fresh (5 minutes)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchMock = fakeApi({ [LIST]: [json({ items: [rock], next_cursor: null })] });

    renderApp('/assets');
    await screen.findByRole('link', { name: /rock_albedo/ });
    await vi.advanceTimersByTimeAsync(4 * 60_000);
    focusManager.setFocused(false);
    focusManager.setFocused(true);
    await vi.advanceTimersByTimeAsync(100);

    expect(countRequests(fetchMock, LIST)).toBe(1);
    focusManager.setFocused(undefined);
    vi.useRealTimers();
  });

  it('shows the count, filters by kind in the URL and says how many of the loaded assets show', async () => {
    fakeApi({ [LIST]: [json({ items: [rock, tree], next_cursor: 'c1' })] });
    const { router } = renderApp('/assets');
    await screen.findByRole('list', { name: 'Assets' });
    const options = screen.getByRole('group', { name: 'Gallery options' });
    expect(within(options).getByText('2 loaded')).toBeInTheDocument();
    expect(within(options).getByRole('radio', { name: 'All' })).toBeChecked();

    await userEvent.click(within(options).getByRole('radio', { name: 'Models' }));

    await waitFor(() => expect(router.state.location.search).toEqual({ kind: 'model' }));
    const list = screen.getByRole('list', { name: 'Assets' });
    expect(
      within(list)
        .getAllByRole('link')
        .map((link) => link.textContent),
    ).toEqual([expect.stringContaining('tree_oak')]);
    expect(within(options).getByText('1 of 2')).toBeInTheDocument();
    expect(screen.getByText('Showing 1 of 2 loaded assets')).toBeInTheDocument();
    // The open asset keeps the gallery's view: the card's link carries the filter.
    expect(within(list).getByRole('link', { name: /tree_oak/ })).toHaveAttribute(
      'href',
      `/assets/${tree.id}?kind=model`,
    );
  });

  it('says when no loaded asset is of the chosen kind, and shows every kind again', async () => {
    fakeApi({ [LIST]: [json({ items: [rock], next_cursor: null })] });
    const { router } = renderApp('/assets?kind=model');

    expect(await screen.findByRole('heading', { name: 'No models loaded' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Show all kinds' }));

    await waitFor(() => expect(router.state.location.search).toEqual({}));
    expect(await screen.findByRole('link', { name: /rock_albedo/ })).toBeInTheDocument();
  });

  it('sorts the loaded assets by name and switches to small cards, both in the URL', async () => {
    const apple = anAsset({ id: '0190f1c2-0000-7000-8000-000000000009', name: 'apple_prop' });
    fakeApi({ [LIST]: [json({ items: [rock, tree, apple], next_cursor: null })] });
    const { router } = renderApp('/assets');
    await screen.findByRole('list', { name: 'Assets' });
    const options = screen.getByRole('group', { name: 'Gallery options' });

    await userEvent.selectOptions(
      within(options).getByRole('combobox', { name: 'Sort' }),
      'Name (A–Z)',
    );
    await userEvent.click(within(options).getByRole('radio', { name: 'Small cards' }));

    await waitFor(() =>
      expect(router.state.location.search).toEqual({ sort: 'name', size: 'small' }),
    );
    const list = screen.getByRole('list', { name: 'Assets' });
    expect(list).toHaveClass('asset-gallery__grid--small');
    expect(
      within(list)
        .getAllByRole('link')
        .map((link) => link.getAttribute('data-asset-id')),
    ).toEqual([apple.id, rock.id, tree.id]);
  });

  it('ignores unknown view options in the URL', async () => {
    fakeApi({ [LIST]: [json({ items: [rock, tree], next_cursor: null })] });

    renderApp('/assets?kind=video&size=huge&sort=random');

    const list = await screen.findByRole('list', { name: 'Assets' });
    expect(within(list).getAllByRole('link')).toHaveLength(2);
    expect(screen.getByRole('radio', { name: 'All' })).toBeChecked();
  });

  it('names each card in full while a long name is cut in the middle', async () => {
    const long = anAsset({
      id: '0190f1c2-0000-7000-8000-000000000010',
      name: 'sunset_matte_painting_background_v3_final',
    });
    fakeApi({ [LIST]: [json({ items: [long], next_cursor: null })] });
    // A 150 px name at 10 px a character, measured the way the browser would.
    vi.stubGlobal(
      'ResizeObserver',
      // eslint-disable-next-line prefer-arrow-callback -- arrow functions cannot be constructed
      vi.fn(function ResizeObserverStub(fit: () => void) {
        return { observe: () => fit(), disconnect: vi.fn() };
      }),
    );
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
      font: '',
      measureText: (value: string) => ({ width: value.length * 10 }),
    } as unknown as CanvasRenderingContext2D);
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(150);

    renderApp('/assets');

    const card = await screen.findByRole('link', {
      name: /sunset_matte_painting_background_v3_final/,
    });
    const name = card.querySelector('.asset-card__name');
    await waitFor(() =>
      expect(name?.querySelector('[aria-hidden="true"]')).toHaveTextContent('sunset_m…_final'),
    );
    expect(within(card).getByRole('tooltip', { hidden: true })).toHaveTextContent(long.name);
  });

  it('offers View in 3D on a model card with a preview, not on an image or a model without one', async () => {
    const crate = anAsset({
      id: '0190f1c2-0000-7000-8000-000000000011',
      name: 'crate',
      kind: 'model',
    });
    fakeApi({ [LIST]: [json({ items: [rock, tree, crate], next_cursor: null })] });

    renderApp('/assets');

    const view = await screen.findByRole('link', { name: 'View crate in 3D' });
    expect(view).toHaveAttribute('href', `/assets/${crate.id}/view`);
    expect(screen.getAllByRole('link', { name: /in 3D/ })).toHaveLength(1);
  });
});
