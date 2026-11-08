import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { aThread, loadImage, serveComments } from '@/test/comment-api';
import { aDetail, anAsset, aVersion } from '@/test/fake-api';
import { renderApp } from '@/test/render-app';
import { setViewportExpanded } from '@/test/viewport';

const asset = anAsset();
const THREADS = '/api/v1/asset-versions/v-1/comment-threads';
const detail = aDetail({
  versions: [aVersion({ id: 'v-1', thumbnail_url: 'http://s3.test/thumbs/v1.webp?sig=1' })],
});

/** Opens Comments with the preview loaded and the overlay laid over a 400 × 200 image box. */
const openWithPreview = async (): Promise<HTMLElement> => {
  renderApp(`/assets/${asset.id}`);
  const article = await screen.findByRole('article', { name: 'rock_albedo' });
  await userEvent.click(within(article).getByRole('tab', { name: 'Comments' }));
  await screen.findByRole('heading', { name: 'No comments yet' });
  loadImage(within(article).getByRole('img', { name: 'Preview of rock_albedo, version 1' }));
  const overlay = await waitFor(() => {
    const found = article.querySelector<HTMLElement>('.region-overlay');
    if (!found) throw new Error('the overlay is not drawn yet');
    return found;
  });
  overlay.getBoundingClientRect = () =>
    ({ left: 100, top: 50, width: 400, height: 200, right: 500, bottom: 250 }) as DOMRect;
  return overlay;
};

const pointer = (
  type: 'pointerDown' | 'pointerMove' | 'pointerUp',
  element: HTMLElement,
  [clientX, clientY]: [number, number],
): void => {
  fireEvent[type](element, { clientX, clientY, button: 0, pointerId: 1 });
};

const post = async (text: string): Promise<void> => {
  await userEvent.type(screen.getByRole('textbox', { name: 'New comment' }), text);
  await userEvent.click(screen.getByRole('button', { name: 'Post comment' }));
};

describe('Marking a region', () => {
  beforeEach(() => setViewportExpanded(true));
  afterEach(() => vi.restoreAllMocks());

  it('marks a centred rectangle from the keyboard: arrows move it, Shift resizes, Enter keeps it', async () => {
    const server = serveComments(detail);
    await openWithPreview();

    await userEvent.click(screen.getByRole('button', { name: 'Mark region' }));
    const draft = screen.getByRole('button', { name: /^Marked region, 40 by 40 percent/ });
    expect(draft).toHaveFocus();
    expect(draft).toHaveAccessibleDescription(/arrows move it, Shift \+ arrows resize it/);
    expect(screen.getByRole('button', { name: 'Mark region' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );

    await userEvent.keyboard(
      '{ArrowRight}{ArrowRight}{ArrowUp}{Shift>}{ArrowRight}{ArrowDown}{/Shift}',
    );
    expect(draft).toHaveAccessibleName(
      'Marked region, 42 by 42 percent, 34 percent from the left and 28 from the top',
    );
    await userEvent.keyboard('{Enter}');

    expect(screen.getByRole('textbox', { name: 'New comment' })).toHaveFocus();
    expect(screen.getByText('Rectangle marked on the image')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Mark again' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
    await post('Warmer here');

    expect(
      await screen.findByRole('button', { name: 'Region 1: Warmer here' }),
    ).toBeInTheDocument();
    expect(server.requests('POST', THREADS)[0]?.body).toEqual({
      body: 'Warmer here',
      region: { shape: 'rect', x: 0.34, y: 0.28, width: 0.42, height: 0.42 },
    });
    expect(screen.queryByText('Rectangle marked on the image')).not.toBeInTheDocument();
  });

  it('keeps a keyboard-moved rectangle inside the image', async () => {
    serveComments(detail);
    await openWithPreview();
    await userEvent.click(screen.getByRole('button', { name: 'Mark region' }));

    await userEvent.keyboard('{ArrowRight>40/}{ArrowDown>40/}');

    expect(screen.getByRole('button', { name: /^Marked region/ })).toHaveAccessibleName(
      'Marked region, 40 by 40 percent, 60 percent from the left and 60 from the top',
    );
  });

  it('cancels marking with Escape: no region, focus back on Mark region', async () => {
    const server = serveComments(detail);
    await openWithPreview();
    await userEvent.click(screen.getByRole('button', { name: 'Mark region' }));

    await userEvent.keyboard('{Escape}');

    expect(screen.queryByRole('button', { name: /^Marked region/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Mark region' })).toHaveFocus();
    await post('No region');
    await screen.findByText('No region');
    expect(server.requests('POST', THREADS)[0]?.body).toEqual({ body: 'No region', region: null });
  });

  it('marks a rectangle by dragging on the image, whichever way the drag goes', async () => {
    const server = serveComments(detail);
    const overlay = await openWithPreview();
    await userEvent.click(screen.getByRole('button', { name: 'Mark region' }));

    pointer('pointerDown', overlay, [400, 200]); // 75 %, 75 %
    pointer('pointerMove', overlay, [300, 150]);
    pointer('pointerUp', overlay, [200, 100]); // 25 %, 25 %

    expect(screen.getByRole('textbox', { name: 'New comment' })).toHaveFocus();
    await post('Dragged');
    await screen.findByRole('button', { name: 'Region 1: Dragged' });
    expect(server.requests('POST', THREADS)[0]?.body).toEqual({
      body: 'Dragged',
      region: { shape: 'rect', x: 0.25, y: 0.25, width: 0.5, height: 0.5 },
    });
  });

  it('marks a pin with a click, and a drag past the edge stops at the edge', async () => {
    const server = serveComments(detail);
    const overlay = await openWithPreview();

    await userEvent.click(screen.getByRole('button', { name: 'Mark region' }));
    pointer('pointerDown', overlay, [140, 90]); // 10 %, 20 %
    pointer('pointerUp', overlay, [141, 90]);
    expect(screen.getByText('Pin marked on the image')).toBeInTheDocument();
    await post('Pinned');
    await screen.findByRole('button', { name: 'Region 1: Pinned' });

    await userEvent.click(screen.getByRole('button', { name: 'Mark region' }));
    pointer('pointerDown', overlay, [300, 150]);
    pointer('pointerUp', overlay, [900, 900]); // far outside the image
    await post('Edge');
    await screen.findByRole('button', { name: 'Region 2: Edge' });

    const bodies = server.requests('POST', THREADS).map((request) => request.body);
    expect(bodies).toEqual([
      { body: 'Pinned', region: { shape: 'point', x: 0.1, y: 0.2 } },
      { body: 'Edge', region: { shape: 'rect', x: 0.5, y: 0.5, width: 0.5, height: 0.5 } },
    ]);
  });

  it('removes a marked region before posting', async () => {
    const server = serveComments(detail);
    await openWithPreview();
    await userEvent.click(screen.getByRole('button', { name: 'Mark region' }));
    await userEvent.keyboard('{Enter}');

    await userEvent.click(screen.getByRole('button', { name: 'Remove region' }));

    expect(screen.getByRole('button', { name: 'Mark region' })).toHaveFocus();
    await post('Plain after all');
    await screen.findByText('Plain after all');
    expect(server.requests('POST', THREADS)[0]?.body).toEqual({
      body: 'Plain after all',
      region: null,
    });
  });

  it('gives a retry without the region a new key, as the API would refuse the old one (KILN-49)', async () => {
    const server = serveComments(detail);
    server.failNext('POST', THREADS, new TypeError('Failed to fetch'));
    await openWithPreview();
    await userEvent.click(screen.getByRole('button', { name: 'Mark region' }));
    await userEvent.keyboard('{Enter}');
    await post('Same words');
    expect(await screen.findByText(/Kiln cannot reach its server/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Remove region' }));
    await userEvent.click(screen.getByRole('button', { name: 'Post comment' }));

    await screen.findByText('Same words');
    const [lost, retry] = server.requests('POST', THREADS);
    expect(lost?.body).toMatchObject({ region: { shape: 'rect' } });
    expect(retry?.body).toEqual({ body: 'Same words', region: null });
    expect(retry?.idempotencyKey).not.toBe(lost?.idempotencyKey);
  });

  it('hides the marks while marking, so a drag over them draws instead', async () => {
    serveComments(detail, {
      threads: {
        'v-1': [
          {
            id: 't-1',
            version_id: 'v-1',
            number: 1,
            region: { shape: 'rect', x: 0, y: 0, width: 1, height: 1 },
            comment: {
              id: 'c-1',
              thread_id: 't-1',
              author: { id: 'u', display_name: 'Bo' },
              body: 'Whole image',
              created_at: '2026-11-06T08:00:00Z',
              edited_at: null,
              deleted: false,
            },
            reply_count: 0,
            resolved_at: null,
            resolved_by: null,
            created_at: '2026-11-06T08:00:00Z',
          },
        ],
      },
    });
    renderApp(`/assets/${asset.id}`);
    const article = await screen.findByRole('article', { name: 'rock_albedo' });
    await userEvent.click(within(article).getByRole('tab', { name: 'Comments' }));
    await screen.findByText('Whole image');
    loadImage(within(article).getByRole('img', { name: 'Preview of rock_albedo, version 1' }));
    const overlay = await waitFor(() => {
      const found = article.querySelector('.region-overlay');
      if (!found) throw new Error('the overlay is not drawn yet');
      return found;
    });

    await userEvent.click(screen.getByRole('button', { name: 'Mark region' }));

    expect(overlay).toHaveClass('region-overlay--marking');
    // The hint shows beside the comment field and is read with the draft.
    const hints = screen.getAllByText(/Drag on the image for a rectangle/);
    expect(hints.map((hint) => hint.className)).toEqual([
      'visually-hidden',
      'comment-composer__hint',
    ]);
  });

  it('says why no region can be marked on a version without a preview', async () => {
    serveComments(
      aDetail({
        versions: [aVersion({ id: 'v-1', status: 'processing', thumbnail_url: null })],
      }),
    );
    renderApp(`/assets/${asset.id}`);
    const article = await screen.findByRole('article', { name: 'rock_albedo' });

    await userEvent.click(within(article).getByRole('tab', { name: 'Comments' }));

    expect(
      await screen.findByText(/This version has no preview yet, so no region can be marked/),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Mark region' })).not.toBeInTheDocument();
  });

  it('leaves the overlay when the Comments tab closes', async () => {
    serveComments(detail);
    await openWithPreview();
    await userEvent.click(screen.getByRole('button', { name: 'Mark region' }));

    await userEvent.click(screen.getByRole('tab', { name: 'Versions 1' }));

    expect(document.querySelector('.region-overlay')).toBeNull();
    expect(screen.getByRole('img', { name: 'Preview of rock_albedo' })).toBeInTheDocument();
  });
});

describe('Badges on a measured image', () => {
  beforeEach(() => setViewportExpanded(true));
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('places each badge in px inside the image and moves one that would cover another', async () => {
    let measure: ResizeObserverCallback = () => undefined;
    vi.stubGlobal(
      'ResizeObserver',
      // eslint-disable-next-line prefer-arrow-callback -- arrow functions cannot be constructed
      vi.fn(function ResizeObserverStub(callback: ResizeObserverCallback) {
        measure = callback;
        return { observe: vi.fn(), disconnect: vi.fn() };
      }),
    );
    const near = (number: number, x: number, y: number) =>
      aThread({
        id: `t-${String(number)}`,
        version_id: 'v-1',
        number,
        body: `Mark ${String(number)}`,
        region: { shape: 'point', x, y, width: null, height: null },
      });
    serveComments(detail, {
      threads: { 'v-1': [near(1, 0.5, 0.5), near(2, 0.51, 0.51), near(3, 1, 1)] },
    });
    renderApp(`/assets/${asset.id}`);
    const article = await screen.findByRole('article', { name: 'rock_albedo' });
    await userEvent.click(within(article).getByRole('tab', { name: 'Comments' }));
    await screen.findByText('Mark 2');
    await userEvent.click(screen.getByRole('button', { name: 'Show more comments' }));
    await screen.findByText('Mark 3');
    loadImage(within(article).getByRole('img', { name: 'Preview of rock_albedo, version 1' }));
    await screen.findByRole('button', { name: 'Region 3: Mark 3' });

    act(() => {
      measure(
        [{ contentRect: { width: 400, height: 200 } } as ResizeObserverEntry],
        {} as ResizeObserver,
      );
    });

    const at = (name: string): string | null =>
      screen.getByRole('button', { name }).getAttribute('style');
    expect(at('Region 1: Mark 1')).toBe('left: 188px; top: 88px;');
    expect(at('Region 2: Mark 2')).not.toBe('left: 190px; top: 90px;'); // moved off badge 1
    expect(at('Region 3: Mark 3')).toBe('left: 376px; top: 176px;'); // the corner, inside
  });
});
