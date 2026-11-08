import { focusManager } from '@tanstack/react-query';
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { assetDetailQueryKey } from '@/constants/assets.constant';
import type { AssetDetail } from '@/interfaces/asset.interface';
import { aDetail, anAsset, aVersion, problem } from '@/test/fake-api';
import { renderApp } from '@/test/render-app';
import { aReviewEvent, serveReviews } from '@/test/review-api';
import { setViewportExpanded } from '@/test/viewport';

const asset = anAsset();
const V1 = aVersion({ id: 'v-1', number: 1, review_state: 'approved', review_revision: 1 });
const V2 = aVersion({ id: 'v-2', number: 2 });
const detail: AssetDetail = aDetail({ versions: [V1, V2] });
const TRANSITIONS = '/api/v1/asset-versions/v-2/review-transitions';
const HISTORY = '/api/v1/asset-versions/v-2/review-history';

const openReview = async (): Promise<HTMLElement> => {
  renderApp(`/assets/${asset.id}`);
  const article = await screen.findByRole('article', { name: 'rock_albedo' });
  await userEvent.click(within(article).getByRole('tab', { name: 'Review' }));
  return article;
};
const form = (number = 2): HTMLElement =>
  screen.getByRole('form', { name: `Decide on version ${String(number)}` });

describe('Review tab', () => {
  let server: ReturnType<typeof serveReviews>;

  beforeEach(() => setViewportExpanded(true));
  afterEach(() => {
    vi.restoreAllMocks();
    focusManager.setFocused(undefined);
  });

  it('opens on the newest version in review, with placeholders, then an empty history', async () => {
    server = serveReviews(detail);

    await openReview();

    expect(screen.getByRole('combobox', { name: 'Review of' })).toHaveValue('v-2');
    expect(screen.getByText('Version 2 is').parentElement).toHaveTextContent('In review');
    expect(within(form()).getByRole('button', { name: 'Approve' })).toBeVisible();
    expect(within(form()).getByRole('button', { name: 'Request changes' })).toBeVisible();
    expect(within(form()).queryByRole('button', { name: 'Reopen' })).not.toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'No decisions yet' })).toBeVisible();
    expect(server.requests('GET', HISTORY)).toHaveLength(1);
  });

  it('shows the asset state in the header and each version state in the Versions tab', async () => {
    server = serveReviews(aDetail({ versions: [V1, V2], review_state: 'in_review' }));
    renderApp(`/assets/${asset.id}`);

    const article = await screen.findByRole('article', { name: 'rock_albedo' });

    expect(within(article).getByRole('banner')).toHaveTextContent('In review');
    const versions = within(article).getAllByRole('listitem');
    expect(versions.map((item) => item.querySelector('[data-review-state]')?.textContent)).toEqual([
      'In review',
      'Approved',
    ]);
  });

  it('fetches no history until the tab is opened', async () => {
    server = serveReviews(detail);
    renderApp(`/assets/${asset.id}`);

    await screen.findByRole('article', { name: 'rock_albedo' });

    expect(server.requests('GET', '/api/v1/asset-versions/')).toHaveLength(0);
  });

  it('approves with the state it saw, a note and a key; the state, badge and history follow', async () => {
    server = serveReviews(detail);
    const article = await openReview();

    await userEvent.type(within(form()).getByRole('textbox', { name: /Note/ }), 'Rim fixed.');
    await userEvent.click(within(form()).getByRole('button', { name: 'Approve' }));

    expect(await screen.findByText('Version 2 approved')).toBeInTheDocument();
    const [request] = server.requests('POST', TRANSITIONS);
    expect(request?.body).toEqual({
      action: 'approve',
      expected_state: 'in_review',
      expected_revision: 0,
      note: 'Rim fixed.',
    });
    expect(request?.idempotencyKey).toMatch(/^[0-9a-f-]{36}$/);
    await waitFor(() =>
      expect(within(form()).getByRole('button', { name: 'Reopen' })).toBeVisible(),
    );
    expect(within(form()).getByRole('textbox', { name: /Note/ })).toHaveValue('');
    expect(screen.getByText('Reopen it to put it back in review and decide again.')).toBeVisible();
    const history = screen.getByRole('region', { name: 'Review history of version 2' });
    expect(await within(history).findByText('Ada Artist approved')).toBeVisible();
    expect(within(history).getByText('Rim fixed.')).toBeVisible();
    expect(within(history).getByText(/from In review to Approved/)).toBeInTheDocument();
    // The asset is approved now: the inspector's header says so in words.
    expect(within(article).getByRole('banner')).toHaveTextContent('Approved');
  });

  it('sends no note when the note is blank', async () => {
    server = serveReviews(detail);
    await openReview();

    await userEvent.type(within(form()).getByRole('textbox', { name: /Note/ }), '   ');
    await userEvent.click(within(form()).getByRole('button', { name: 'Request changes' }));

    expect(await screen.findByText('Changes requested on version 2')).toBeInTheDocument();
    expect(server.requests('POST', TRANSITIONS)[0]?.body).toMatchObject({ note: null });
  });

  it('says who won when someone else decided first, keeps the note and offers what applies now', async () => {
    server = serveReviews(detail);
    await openReview();
    server.decideAsSomeoneElse('v-2', 'approve');

    await userEvent.type(within(form()).getByRole('textbox', { name: /Note/ }), 'Too dark.');
    await userEvent.click(within(form()).getByRole('button', { name: 'Request changes' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(
      'Someone else decided first: this version is now “Approved”. Check it, then decide again. Your note is kept.',
    );
    await waitFor(() => expect(alert).toHaveFocus());
    await waitFor(() =>
      expect(within(form()).getByRole('button', { name: 'Reopen' })).toBeVisible(),
    );
    expect(within(form()).getByRole('textbox', { name: /Note/ })).toHaveValue('Too dark.');
    expect(screen.getByText('Version 2 is').parentElement).toHaveTextContent('Approved');
    expect(await screen.findByText('Bo Lead approved')).toBeVisible();
  });

  it('refuses a decision on an older revision of the same state (approve, then reopen)', async () => {
    server = serveReviews(detail);
    await openReview();
    server.decideAsSomeoneElse('v-2', 'approve');
    server.decideAsSomeoneElse('v-2', 'reopen');

    await userEvent.click(within(form()).getByRole('button', { name: 'Approve' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('this version is now “In review”');
    expect(server.requests('POST', TRANSITIONS)[0]?.body).toMatchObject({ expected_revision: 0 });
    // The refetched version carries the new revision: the next approve goes through.
    expect(await screen.findByText('Bo Lead reopened')).toBeVisible();
    await userEvent.click(within(form()).getByRole('button', { name: 'Approve' }));
    expect(await screen.findByText('Version 2 approved')).toBeInTheDocument();
    expect(server.requests('POST', TRANSITIONS)[1]?.body).toMatchObject({ expected_revision: 2 });
    // Only the revision changed, and it is in the key's signature: a new key (KILN-49).
    const [first, second] = server.requests('POST', TRANSITIONS).map((r) => r.idempotencyKey);
    expect(second).not.toBe(first);
  });

  it('starts each version with an empty form, and a new key, after a lost answer', async () => {
    server = serveReviews(aDetail({ versions: [aVersion({ id: 'v-1', number: 1 }), V2] }));
    server.failNext('POST', TRANSITIONS, new TypeError('Failed to fetch'));
    await openReview();
    await userEvent.type(within(form()).getByRole('textbox', { name: /Note/ }), 'Looks right.');
    await userEvent.click(within(form()).getByRole('button', { name: 'Approve' }));
    expect(await screen.findByRole('alert')).toBeVisible();

    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Review of' }), 'v-1');

    expect(screen.getByRole('combobox', { name: 'Review of' })).toHaveFocus();
    expect(within(form(1)).getByRole('textbox', { name: /Note/ })).toHaveValue('');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    await userEvent.type(within(form(1)).getByRole('textbox', { name: /Note/ }), 'Looks right.');
    await userEvent.click(within(form(1)).getByRole('button', { name: 'Approve' }));
    expect(await screen.findByText('Version 1 approved')).toBeInTheDocument();
    const [onV2] = server.requests('POST', TRANSITIONS);
    const [onV1] = server.requests('POST', '/api/v1/asset-versions/v-1/review-transitions');
    expect(onV1?.idempotencyKey).not.toBe(onV2?.idempotencyKey);
  });

  it('retries a lost answer with the same key, so a decision is never made twice', async () => {
    server = serveReviews(detail);
    server.failNext('POST', TRANSITIONS, new TypeError('Failed to fetch'));
    await openReview();

    await userEvent.click(within(form()).getByRole('button', { name: 'Approve' }));
    expect(await screen.findByRole('alert')).toBeVisible();
    await userEvent.click(within(form()).getByRole('button', { name: 'Approve' }));

    expect(await screen.findByText('Version 2 approved')).toBeInTheDocument();
    const keys = server.requests('POST', TRANSITIONS).map((request) => request.idempotencyKey);
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
  });

  it.each([
    ['note', 'Approve', 'Rim fixed, edges too.'],
    ['action', 'Request changes', 'Rim fixed.'],
  ])(
    'gives a retry with another %s a new key, so it is never refused as a reused key (KILN-49)',
    async (_changed, button, note) => {
      server = serveReviews(detail);
      server.failNext('POST', TRANSITIONS, new TypeError('Failed to fetch'));
      await openReview();
      const field = (): HTMLElement => within(form()).getByRole('textbox', { name: /Note/ });
      await userEvent.type(field(), 'Rim fixed.');
      await userEvent.click(within(form()).getByRole('button', { name: 'Approve' }));
      const alert = await screen.findByRole('alert');
      await waitFor(() => expect(alert).toHaveFocus());

      await userEvent.clear(field());
      await userEvent.type(field(), note);
      expect(field()).toHaveValue(note);
      await userEvent.click(within(form()).getByRole('button', { name: button }));

      await waitFor(() => expect(server.requests('POST', TRANSITIONS)).toHaveLength(2));
      const [lost, retry] = server.requests('POST', TRANSITIONS);
      expect(retry?.body).toMatchObject({ note });
      expect(retry?.idempotencyKey).toMatch(/^[0-9a-f-]{36}$/);
      expect(retry?.idempotencyKey).not.toBe(lost?.idempotencyKey);
    },
  );

  it.each([
    ['INVALID_REVIEW_NOTE', 422, 'The note is too long or has hidden characters.'],
    ['INSUFFICIENT_SCOPE', 403, 'Your access is read-only, so you cannot review.'],
    ['VERSION_NOT_READY', 409, 'This version is not ready to be reviewed'],
  ])('explains a refusal (%s) in words', async (code, status, message) => {
    server = serveReviews(detail);
    server.failNext('POST', TRANSITIONS, problem(status, 'Refused', code));
    await openReview();

    await userEvent.click(within(form()).getByRole('button', { name: 'Approve' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(message);
    // Approve is still offered, but focus goes to the message so it is read first (KILN-48).
    await waitFor(() => expect(alert).toHaveFocus());
  });

  describe('focus after a decision (KILN-48, WCAG 2.4.3)', () => {
    const status = (): HTMLElement =>
      screen.getAllByRole('status').find((node) => node.getAttribute('aria-live') === 'polite') ??
      screen.getByRole('status');

    it('moves to Reopen once Approve is gone, and back to Approve after reopening', async () => {
      server = serveReviews(detail);
      await openReview();

      await userEvent.click(within(form()).getByRole('button', { name: 'Approve' }));
      const reopen = await within(form()).findByRole('button', { name: 'Reopen' });
      await waitFor(() => expect(document.activeElement).toBe(reopen));
      // Said once, by the polite status; the focused button adds only its own name.
      expect(status()).toHaveTextContent(/^Version 2 approved$/);

      await userEvent.keyboard('{Enter}');
      const approve = await within(form()).findByRole('button', { name: 'Approve' });
      await waitFor(() => expect(document.activeElement).toBe(approve));
      expect(status()).toHaveTextContent(/^Version 2 approvedVersion 2 is back in review$/);
    });

    it('moves to Reopen after changes are requested', async () => {
      server = serveReviews(detail);
      await openReview();

      await userEvent.click(within(form()).getByRole('button', { name: 'Request changes' }));

      const reopen = await within(form()).findByRole('button', { name: 'Reopen' });
      await waitFor(() => expect(document.activeElement).toBe(reopen));
    });

    it('moves to the state line when the new state offers no action', async () => {
      const failed = aVersion({
        id: 'v-2',
        number: 1,
        status: 'failed',
        review_state: 'approved',
        review_revision: 1,
      });
      server = serveReviews(aDetail({ versions: [failed] }));
      await openReview();

      await userEvent.click(within(form(1)).getByRole('button', { name: 'Reopen' }));

      expect(await screen.findByText('Version 1 is back in review')).toBeInTheDocument();
      const stateLine = screen.getByText('Version 1 is').parentElement;
      await waitFor(() => expect(document.activeElement).toBe(stateLine));
      expect(stateLine).toHaveAttribute('tabindex', '-1');
      expect(stateLine).toHaveTextContent('In review');
    });

    it('moves focus once per decision, never again when someone else decides later', async () => {
      server = serveReviews(detail);
      const { queryClient } = renderApp(`/assets/${asset.id}`);
      const article = await screen.findByRole('article', { name: 'rock_albedo' });
      await userEvent.click(within(article).getByRole('tab', { name: 'Review' }));
      await userEvent.click(within(form()).getByRole('button', { name: 'Approve' }));
      const reopen = await within(form()).findByRole('button', { name: 'Reopen' });
      await waitFor(() => expect(reopen).toHaveFocus());
      const note = within(form()).getByRole('textbox', { name: /Note/ });
      await userEvent.click(note);

      // Someone else reopens; the page learns it on its next fetch of the asset (stale data).
      server.decideAsSomeoneElse('v-2', 'reopen');
      await act(() => queryClient.invalidateQueries({ queryKey: assetDetailQueryKey(asset.id) }));

      await within(form()).findByRole('button', { name: 'Approve' });
      expect(note).toHaveFocus();
    });

    it('ignores a held Enter, so it never presses the action that took focus', async () => {
      server = serveReviews(detail);
      await openReview();
      const approve = within(form()).getByRole('button', { name: 'Approve' });

      // fireEvent returns false when the default (the button's activation) was prevented.
      expect(fireEvent.keyDown(approve, { key: 'Enter', repeat: true })).toBe(false);
      expect(fireEvent.keyDown(approve, { key: 'Enter' })).toBe(true);
    });
  });

  it('offers only Reopen on a decided version, and reopens it', async () => {
    server = serveReviews(detail, { 'v-1': [aReviewEvent({ version_id: 'v-1' })] });
    await openReview();

    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Review of' }), 'v-1');

    expect(within(form(1)).queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
    await userEvent.click(within(form(1)).getByRole('button', { name: 'Reopen' }));
    expect(await screen.findByText('Version 1 is back in review')).toBeInTheDocument();
    expect(
      server.requests('POST', '/api/v1/asset-versions/v-1/review-transitions')[0]?.body,
    ).toEqual({ action: 'reopen', expected_state: 'approved', expected_revision: 1, note: null });
  });

  it('says a version still processing cannot be decided yet, and offers no decision', async () => {
    server = serveReviews(
      aDetail({ versions: [aVersion({ id: 'v-2', number: 1, status: 'processing' })] }),
    );
    await openReview();

    expect(
      screen.getByText(
        'This version can be approved or sent back once it has finished processing.',
      ),
    ).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: /Note/ })).not.toBeInTheDocument();
  });

  it('lists the history newest first, page by page, with notes as text', async () => {
    server = serveReviews(detail, {
      'v-2': [
        aReviewEvent({ version_id: 'v-2', sequence: 3, action: 'approve', note: '<b>ok</b>' }),
        aReviewEvent({
          version_id: 'v-2',
          sequence: 2,
          action: 'reopen',
          from_state: 'changes_requested',
          to_state: 'in_review',
        }),
        aReviewEvent({
          version_id: 'v-2',
          sequence: 1,
          action: 'request_changes',
          to_state: 'changes_requested',
          note: 'Darker rim',
        }),
      ],
    });
    await openReview();

    const history = screen.getByRole('region', { name: 'Review history of version 2' });
    const items = await within(history).findAllByRole('listitem');
    expect(items.map((item) => item.firstElementChild?.nextElementSibling?.textContent)).toEqual([
      'Ada Artist approved, from In review to Approved',
      'Ada Artist reopened, from Changes requested to In review',
    ]);
    expect(within(history).getByText('<b>ok</b>').querySelector('b')).toBeNull();

    await userEvent.click(within(history).getByRole('button', { name: 'Show older' }));

    expect(await within(history).findByText('Darker rim')).toBeVisible();
    expect(server.requests('GET', HISTORY).at(-1)?.path).toContain('cursor=2');
  });

  it('says when the history fails to load, and Try again fetches it', async () => {
    server = serveReviews(detail, { 'v-2': [aReviewEvent({ version_id: 'v-2', note: 'Back' })] });
    for (let attempt = 0; attempt < 3; attempt += 1) {
      server.failNext('GET', HISTORY, problem(503, 'Service Unavailable', 'DATABASE_UNAVAILABLE'));
    }
    await openReview();

    expect(await screen.findByText('The review history did not load')).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Back')).toBeVisible();
  });

  it('fetches the history again when the window regains focus', async () => {
    server = serveReviews(detail);
    await openReview();
    await screen.findByRole('heading', { name: 'No decisions yet' });

    act(() => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
    });

    await waitFor(() => expect(server.requests('GET', HISTORY)).toHaveLength(2));
  });
});
