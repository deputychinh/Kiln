import { focusManager } from '@tanstack/react-query';
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import type { AssetDetail } from '@/interfaces/asset.interface';
import { aComment, anotherPerson, aThread, loadImage, serveComments } from '@/test/comment-api';
import { aDetail, anAsset, aVersion, problem } from '@/test/fake-api';
import { renderApp } from '@/test/render-app';
import { setViewportExpanded } from '@/test/viewport';

const asset = anAsset();
const V1 = aVersion({
  id: 'v-1',
  number: 1,
  thumbnail_url: 'http://s3.test/thumbs/v1.webp?sig=1',
});
const V2 = aVersion({
  id: 'v-2',
  number: 2,
  thumbnail_url: 'http://s3.test/thumbs/v2.webp?sig=1',
});
const detail: AssetDetail = aDetail({ versions: [V1, V2] });
const THREADS = '/api/v1/asset-versions/v-2/comment-threads';

const openComments = async (): Promise<HTMLElement> => {
  renderApp(`/assets/${asset.id}`);
  const article = await screen.findByRole('article', { name: 'rock_albedo' });
  await userEvent.click(within(article).getByRole('tab', { name: 'Comments' }));
  return article;
};

/** What a screen reader meets at `focusin`: the field must already describe its error. */
const recordFocusIn = (field: HTMLElement): string[] => {
  const seen: string[] = [];
  field.addEventListener('focusin', () => {
    const describedBy = field.getAttribute('aria-describedby') ?? '';
    const description = describedBy
      .split(' ')
      .map((id) => document.getElementById(id)?.textContent ?? '')
      .join(' ');
    seen.push(`${String(field.getAttribute('aria-invalid'))} | ${description}`);
  });
  return seen;
};

describe('Comments tab', () => {
  let server: ReturnType<typeof serveComments>;

  beforeEach(() => setViewportExpanded(true));
  afterEach(() => {
    vi.restoreAllMocks();
    focusManager.setFocused(undefined);
  });

  it('shows placeholders while loading, then says how to start when there are none', async () => {
    server = serveComments(detail);

    await openComments();

    expect(await screen.findByRole('heading', { name: 'No comments yet' })).toBeInTheDocument();
    expect(screen.getByText(/Write the first one above/)).toBeInTheDocument();
    expect(server.requests('GET', THREADS)).toHaveLength(1);
    expect(server.requests('GET', '/api/v1/asset-versions/v-1')).toHaveLength(0);
  });

  it('fetches no comments until the tab is opened', async () => {
    server = serveComments(detail);
    renderApp(`/assets/${asset.id}`);

    await screen.findByRole('article', { name: 'rock_albedo' });

    expect(server.requests('GET', '/api/v1/asset-versions/')).toHaveLength(0);
  });

  it('says when comments fail to load, and Try again fetches them', async () => {
    server = serveComments(detail, { threads: { 'v-2': [aThread({ body: 'Back again' })] } });
    server.failNext('GET', THREADS, problem(503, 'Service Unavailable', 'DATABASE_UNAVAILABLE'));
    server.failNext('GET', THREADS, problem(503, 'Service Unavailable', 'DATABASE_UNAVAILABLE'));
    server.failNext('GET', THREADS, problem(503, 'Service Unavailable', 'DATABASE_UNAVAILABLE'));

    await openComments();

    expect(await screen.findByText('Comments did not load')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Back again')).toBeInTheDocument();
  });

  it('lists threads by number with their author, region and replies, page by page', async () => {
    server = serveComments(detail, {
      threads: {
        'v-2': [
          aThread({ id: 't-1', number: 1, body: 'Rim too bright' }),
          aThread({
            id: 't-2',
            number: 2,
            body: 'Whole thing',
            region: null,
            author: anotherPerson(),
          }),
          aThread({ id: 't-3', number: 3, body: 'Third note' }),
        ],
      },
    });

    await openComments();

    const list = await screen.findByRole('region', { name: 'Comments on version 2' });
    await within(list).findByText('Rim too bright');
    expect(within(list).getByRole('article', { name: 'Comment 1 by Ada Artist' })).toBeVisible();
    expect(within(list).getByRole('article', { name: 'Comment 2 by Bo Lead' })).toHaveTextContent(
      'Whole version',
    );
    expect(within(list).getByRole('button', { name: 'Show region 1 on the image' })).toBeVisible();
    expect(within(list).queryByText('Third note')).not.toBeInTheDocument();

    await userEvent.click(within(list).getByRole('button', { name: 'Show more comments' }));

    expect(await within(list).findByText('Third note')).toBeInTheDocument();
    expect(server.requests('GET', THREADS).at(-1)?.path).toContain('cursor=2');
  });

  it('keeps long and multi-line comments as text, never as markup', async () => {
    const long = `${'word '.repeat(300)}\nsecond line <b>not bold</b>`;
    server = serveComments(detail, { threads: { 'v-2': [aThread({ body: long })] } });

    await openComments();

    const body = await screen.findByText((_text, element) =>
      Boolean(element?.classList.contains('comment-entry__body')),
    );
    expect(body.textContent).toBe(long);
    expect(body.querySelector('b')).toBeNull();
  });

  it('posts a plain comment with an idempotency key and announces it', async () => {
    server = serveComments(detail);
    await openComments();
    await screen.findByRole('heading', { name: 'No comments yet' });

    await userEvent.type(screen.getByRole('textbox', { name: 'New comment' }), 'Looks good');
    await userEvent.click(screen.getByRole('button', { name: 'Post comment' }));

    expect(await screen.findByText('Looks good')).toBeInTheDocument();
    const [post] = server.requests('POST', THREADS);
    expect(post?.body).toEqual({ body: 'Looks good', region: null });
    expect(post?.idempotencyKey).toMatch(/^[0-9a-f-]{36}$/);
    expect(screen.getByRole('textbox', { name: 'New comment' })).toHaveValue('');
    expect(await screen.findByText('Comment 1 posted')).toBeInTheDocument();
  });

  it('asks for text before posting and sends nothing', async () => {
    server = serveComments(detail);
    await openComments();
    await screen.findByRole('heading', { name: 'No comments yet' });

    const field = screen.getByRole('textbox', { name: 'New comment' });
    const seen = recordFocusIn(field);
    await userEvent.click(screen.getByRole('button', { name: 'Post comment' }));

    expect(field).toHaveAccessibleDescription('Write a comment first.');
    await waitFor(() => expect(field).toHaveFocus());
    // Focus arrives once the field describes its error (KILN-48 review round 3).
    expect(seen).toEqual(['true | Write a comment first.']);
    expect(server.requests('POST', THREADS)).toHaveLength(0);
  });

  it('retries a failed post with the same key, so it can never post twice', async () => {
    server = serveComments(detail);
    server.failNext('POST', THREADS, new TypeError('Failed to fetch'));
    await openComments();
    await screen.findByRole('heading', { name: 'No comments yet' });
    await userEvent.type(screen.getByRole('textbox', { name: 'New comment' }), 'Once');

    await userEvent.click(screen.getByRole('button', { name: 'Post comment' }));
    expect(
      await screen.findByText(
        'Kiln cannot reach its server. Check your connection, then try again.',
      ),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Post comment' }));
    await screen.findByText('Once');

    const [first, second] = server.requests('POST', THREADS);
    expect(first?.idempotencyKey).toBe(second?.idempotencyKey);
    await userEvent.type(screen.getByRole('textbox', { name: 'New comment' }), 'Twice');
    await userEvent.click(screen.getByRole('button', { name: 'Post comment' }));
    await screen.findByText('Twice');
    expect(server.requests('POST', THREADS)[2]?.idempotencyKey).not.toBe(first?.idempotencyKey);
  });

  it('gives a retry with another body a new key, for a comment and a reply (KILN-49)', async () => {
    server = serveComments(detail, { threads: { 'v-2': [aThread({ id: 't-1' })] } });
    const replies = '/api/v1/comment-threads/t-1/comments';
    server.failNext('POST', THREADS, new TypeError('Failed to fetch'));
    server.failNext('POST', replies, new TypeError('Failed to fetch'));
    await openComments();
    const composer = await screen.findByRole('textbox', { name: 'New comment' });
    await userEvent.type(composer, 'Draft');
    await userEvent.click(screen.getByRole('button', { name: 'Post comment' }));
    await screen.findAllByText(/Kiln cannot reach its server/);
    await userEvent.type(composer, ', edited');
    await userEvent.click(screen.getByRole('button', { name: 'Post comment' }));
    await screen.findByText('Draft, edited');

    await userEvent.click(screen.getByRole('button', { name: 'Reply to comment 1' }));
    const reply = screen.getByRole('textbox', { name: 'Reply to comment 1' });
    await userEvent.type(reply, 'Reply');
    await userEvent.click(screen.getByRole('button', { name: 'Post reply' }));
    await waitFor(() => expect(server.requests('POST', replies)).toHaveLength(1));
    await screen.findAllByText(/Kiln cannot reach its server/);
    await userEvent.type(reply, ', edited');
    await userEvent.click(screen.getByRole('button', { name: 'Post reply' }));
    await waitFor(() => expect(server.requests('POST', replies)).toHaveLength(2));

    for (const [path, words] of [
      [THREADS, 'Draft'],
      [replies, 'Reply'],
    ] as const) {
      const [lost, retry] = server.requests('POST', path);
      expect(lost?.body).toMatchObject({ body: words });
      expect(retry?.body).toMatchObject({ body: `${words}, edited` });
      expect(retry?.idempotencyKey).not.toBe(lost?.idempotencyKey);
    }
  });

  describe('focus on a field that describes its error (KILN-48)', () => {
    const unreachable = /^true \| .*Kiln cannot reach its server/;

    it('a failed new comment', async () => {
      server = serveComments(detail);
      server.failNext('POST', THREADS, new TypeError('Failed to fetch'));
      await openComments();
      const composer = await screen.findByRole('textbox', { name: 'New comment' });
      await userEvent.type(composer, 'Lost');
      const seen = recordFocusIn(composer);
      await userEvent.click(screen.getByRole('button', { name: 'Post comment' }));

      await waitFor(() => expect(composer).toHaveFocus());
      expect(seen).toHaveLength(1);
      expect(seen[0]).toMatch(unreachable);
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });

    it('a failed reply, and a blank one', async () => {
      server = serveComments(detail, { threads: { 'v-2': [aThread({ id: 't-1' })] } });
      server.failNext(
        'POST',
        '/api/v1/comment-threads/t-1/comments',
        new TypeError('Failed to fetch'),
      );
      await openComments();
      const thread = await screen.findByRole('article', { name: 'Comment 1 by Ada Artist' });
      await userEvent.click(within(thread).getByRole('button', { name: 'Reply to comment 1' }));
      const reply = within(thread).getByRole('textbox', { name: 'Reply to comment 1' });
      await userEvent.type(reply, 'Lost');
      const seen = recordFocusIn(reply);
      await userEvent.click(within(thread).getByRole('button', { name: 'Post reply' }));
      await waitFor(() => expect(reply).toHaveFocus());

      await userEvent.clear(reply);
      await userEvent.click(within(thread).getByRole('button', { name: 'Post reply' }));
      await waitFor(() => expect(seen).toHaveLength(2));

      expect(seen[0]).toMatch(unreachable);
      expect(seen[1]).toMatch(/^true \| .*Write a comment first/);
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });

    it('a failed edit, and a blank one', async () => {
      server = serveComments(detail, {
        threads: { 'v-2': [aThread({ id: 't-1', body: 'Mine' })] },
      });
      server.failNext('PATCH', '/api/v1/comments/', new TypeError('Failed to fetch'));
      await openComments();
      const thread = await screen.findByRole('article', { name: 'Comment 1 by Ada Artist' });
      await userEvent.click(within(thread).getByRole('button', { name: 'Edit' }));
      const edit = within(thread).getByRole('textbox', { name: 'Edit comment' });
      await userEvent.type(edit, ' again');
      const seen = recordFocusIn(edit);
      await userEvent.click(within(thread).getByRole('button', { name: 'Save' }));

      await waitFor(() => expect(edit).toHaveFocus());
      expect(seen).toHaveLength(1);
      expect(seen[0]).toMatch(unreachable);

      // Blank: Save takes focus, then the field gets it back once it says why (review round 3).
      await userEvent.clear(edit);
      await userEvent.click(within(thread).getByRole('button', { name: 'Save' }));
      await waitFor(() => expect(seen).toHaveLength(2));
      expect(seen[1]).toMatch(/^true \| .*Write a comment first/);
      expect(edit).toHaveFocus();
    });
  });

  it('explains a refusal from the API in words', async () => {
    server = serveComments(detail);
    server.failNext('POST', THREADS, problem(403, 'Forbidden', 'INSUFFICIENT_SCOPE'));
    await openComments();
    await screen.findByRole('heading', { name: 'No comments yet' });
    await userEvent.type(screen.getByRole('textbox', { name: 'New comment' }), 'Hi');

    await userEvent.click(screen.getByRole('button', { name: 'Post comment' }));

    expect(
      await screen.findByText('Your access is read-only, so you cannot comment.'),
    ).toBeInTheDocument();
  });

  it('replies to a thread, then shows the replies, oldest first, page by page', async () => {
    server = serveComments(detail, {
      threads: { 'v-2': [aThread({ id: 't-1', reply_count: 3 })] },
      replies: {
        't-1': [
          aComment({ thread_id: 't-1', body: 'First reply' }),
          aComment({ thread_id: 't-1', body: 'Second reply' }),
          aComment({ thread_id: 't-1', body: 'Third reply' }),
        ],
      },
    });
    await openComments();

    const toggle = await screen.findByRole('button', { name: 'Show 3 replies' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(toggle);
    const replies = await screen.findByRole('list', { name: 'Replies to comment 1' });
    expect(await within(replies).findByText('First reply')).toBeInTheDocument();
    expect(within(replies).queryByText('Third reply')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Show more replies' }));
    expect(await within(replies).findByText('Third reply')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Reply to comment 1' }));
    const field = screen.getByRole('textbox', { name: 'Reply to comment 1' });
    expect(field).toHaveFocus();
    await userEvent.type(field, 'On it');
    await userEvent.click(screen.getByRole('button', { name: 'Post reply' }));

    expect(await screen.findByText('On it')).toBeInTheDocument();
    expect(server.requests('POST', '/api/v1/comment-threads/t-1/comments')[0]?.body).toEqual({
      body: 'On it',
    });
    expect(screen.getByRole('button', { name: 'Reply to comment 1' })).toHaveFocus();
    expect(screen.getByRole('button', { name: 'Hide replies' })).toBeInTheDocument();
  });

  it('cancels a reply with Escape and gives focus back to Reply', async () => {
    server = serveComments(detail, { threads: { 'v-2': [aThread({ id: 't-1' })] } });
    await openComments();
    await userEvent.click(await screen.findByRole('button', { name: 'Reply to comment 1' }));

    await userEvent.type(screen.getByRole('textbox', { name: 'Reply to comment 1' }), 'Draft');
    await userEvent.keyboard('{Escape}');

    expect(screen.queryByRole('textbox', { name: 'Reply to comment 1' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reply to comment 1' })).toHaveFocus();
  });

  it('offers Edit and Delete only on my own comments, and edits in place', async () => {
    server = serveComments(detail, {
      threads: {
        'v-2': [
          aThread({ id: 't-1', number: 1, body: 'Mine' }),
          aThread({ id: 't-2', number: 2, body: 'Theirs', author: anotherPerson() }),
        ],
      },
    });
    await openComments();
    const mine = await screen.findByRole('article', { name: 'Comment 1 by Ada Artist' });
    const theirs = screen.getByRole('article', { name: 'Comment 2 by Bo Lead' });
    expect(within(theirs).queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
    expect(within(theirs).queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();

    await userEvent.click(within(mine).getByRole('button', { name: 'Edit' }));
    const field = within(mine).getByRole('textbox', { name: 'Edit comment' });
    expect(field).toHaveFocus();
    await userEvent.clear(field);
    await userEvent.type(field, 'Mine, better');
    await userEvent.click(within(mine).getByRole('button', { name: 'Save' }));

    expect(await within(mine).findByText('Mine, better')).toBeInTheDocument();
    expect(within(mine).getByText(/edited/)).toBeInTheDocument();
    expect(within(mine).getByRole('button', { name: 'Edit' })).toHaveFocus();
  });

  it('deletes my comment after confirming; Escape cancels with focus back on Delete', async () => {
    server = serveComments(detail, { threads: { 'v-2': [aThread({ id: 't-1', body: 'Oops' })] } });
    await openComments();
    const mine = await screen.findByRole('article', { name: 'Comment 1 by Ada Artist' });

    await userEvent.click(within(mine).getByRole('button', { name: 'Delete' }));
    expect(within(mine).getByText('Delete this comment? Replies stay.')).toBeInTheDocument();
    expect(within(mine).getByRole('button', { name: 'Delete comment' })).toHaveFocus();
    await userEvent.keyboard('{Escape}');
    expect(within(mine).getByRole('button', { name: 'Delete' })).toHaveFocus();
    expect(server.requests('DELETE', '/api/v1/comments/')).toHaveLength(0);

    await userEvent.click(within(mine).getByRole('button', { name: 'Delete' }));
    await userEvent.click(within(mine).getByRole('button', { name: 'Delete comment' }));

    expect(await within(mine).findByText('Comment deleted')).toBeInTheDocument();
    expect(within(mine).queryByText('Oops')).not.toBeInTheDocument();
    expect(within(mine).queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
    // "Delete comment" is gone: focus goes to the thread, not to <body> (KILN-48, WCAG 2.4.3).
    await waitFor(() => expect(document.activeElement).toBe(mine));
  });

  it('puts focus on the thread after deleting a reply, whose buttons are gone', async () => {
    server = serveComments(detail, {
      threads: { 'v-2': [aThread({ id: 't-1', reply_count: 1 })] },
      replies: { 't-1': [aComment({ thread_id: 't-1', body: 'Wrong reply' })] },
    });
    await openComments();
    const thread = await screen.findByRole('article', { name: 'Comment 1 by Ada Artist' });
    await userEvent.click(within(thread).getByRole('button', { name: 'Show 1 reply' }));
    const replies = await within(thread).findByRole('list', { name: 'Replies to comment 1' });
    await within(replies).findByText('Wrong reply');

    await userEvent.click(within(replies).getByRole('button', { name: 'Delete' }));
    await userEvent.keyboard('{Enter}');

    expect(await within(replies).findByText('Comment deleted')).toBeInTheDocument();
    await waitFor(() => expect(document.activeElement).toBe(thread));
    expect(
      screen.getByText('Comment deleted', { selector: '[role="status"] *' }),
    ).toBeInTheDocument();
  });

  it('resolves a thread out of the list, shows it again on request, and reopens it', async () => {
    server = serveComments(detail, {
      threads: { 'v-2': [aThread({ id: 't-1', body: 'Fix the rim' })] },
    });
    await openComments();
    const item = await screen.findByRole('article', { name: 'Comment 1 by Ada Artist' });

    await userEvent.click(within(item).getByRole('button', { name: 'Resolve' }));

    expect(await screen.findByText('Every comment on this version is resolved.')).toBeVisible();
    expect(screen.queryByText('Fix the rim')).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Comments on version 2' })).toHaveFocus();
    expect(screen.getByText('Comment 1 resolved')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('checkbox', { name: 'Show resolved (1)' }));
    const resolved = screen.getByRole('article', { name: 'Comment 1 by Ada Artist' });
    expect(resolved).toHaveTextContent('Resolved by Ada Artist');
    await userEvent.click(within(resolved).getByRole('button', { name: 'Reopen' }));

    await waitFor(() => expect(resolved).not.toHaveTextContent('Resolved by'));
    expect(server.requests('PATCH', '/api/v1/comment-threads/t-1').map((r) => r.body)).toEqual([
      { resolved: true },
      { resolved: false },
    ]);
  });

  it('switches to another version: its threads and its preview', async () => {
    server = serveComments(detail, {
      threads: {
        'v-1': [aThread({ id: 't-old', version_id: 'v-1', body: 'On version one' })],
        'v-2': [aThread({ id: 't-new', body: 'On version two' })],
      },
    });
    const article = await openComments();
    await screen.findByText('On version two');
    expect(
      within(article).getByRole('img', { name: 'Preview of rock_albedo, version 2' }),
    ).toHaveAttribute('src', V2.thumbnail_url);

    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Comments on' }), 'v-1');

    expect(await screen.findByText('On version one')).toBeInTheDocument();
    expect(screen.queryByText('On version two')).not.toBeInTheDocument();
    expect(
      within(article).getByRole('img', { name: 'Preview of rock_albedo, version 1' }),
    ).toHaveAttribute('src', V1.thumbnail_url);
    expect(screen.getByRole('option', { name: 'Version 2 (newest)' })).toBeInTheDocument();
  });

  it('opens on the newest ready version, not a newer one still processing', async () => {
    const processing = aVersion({
      id: 'v-3',
      number: 3,
      status: 'processing',
      thumbnail_url: null,
    });
    server = serveComments(aDetail({ versions: [V1, V2, processing] }));

    await openComments();

    await screen.findByRole('heading', { name: 'No comments yet' });
    expect(screen.getByRole('combobox', { name: 'Comments on' })).toHaveValue('v-2');
  });

  it('fetches the threads again when the window regains focus', async () => {
    server = serveComments(detail);
    await openComments();
    await screen.findByRole('heading', { name: 'No comments yet' });
    server.threads.set('v-2', [aThread({ body: 'From a colleague', author: anotherPerson() })]);

    act(() => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
    });

    expect(await screen.findByText('From a colleague')).toBeInTheDocument();
    expect(server.requests('GET', THREADS).length).toBeGreaterThanOrEqual(2);
  });

  it('offers plain comments only on a 3D model, and says why', async () => {
    const model = aDetail({
      kind: 'model',
      versions: [
        aVersion({ id: 'v-m', content_type: 'model/gltf-binary', file_name: 'crate.glb' }),
      ],
    });
    server = serveComments(model);

    await openComments();

    expect(
      await screen.findByText(
        'Comments on a 3D model apply to all of it; regions mark images only.',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Mark region' })).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: 'Comments on' })).not.toBeInTheDocument();
  });

  it('draws each open thread on the image as a numbered button that selects its thread', async () => {
    server = serveComments(detail, {
      threads: {
        'v-2': [
          aThread({ id: 't-1', number: 1, body: 'The rim is too bright and the edge glows' }),
          aThread({
            id: 't-2',
            number: 2,
            body: 'Pin here',
            region: { shape: 'point', x: 0.1, y: 0.9, width: null, height: null },
          }),
          aThread({ id: 't-3', number: 3, body: 'Plain', region: null }),
          aThread({ id: 't-4', number: 4, body: 'Done', resolved_at: '2026-11-06T09:00:00Z' }),
        ],
      },
    });
    const article = await openComments();
    await screen.findByText('Pin here');
    loadImage(within(article).getByRole('img', { name: 'Preview of rock_albedo, version 2' }));

    const marks = await within(article).findByRole('group', { name: 'Marked regions' });
    const buttons = within(marks).getAllByRole('button');
    expect(buttons.map((button) => button.getAttribute('aria-label'))).toEqual([
      'Region 1: The rim is too bright and the edge glows',
      'Region 2: Pin here',
    ]);
    // The outline is drawn at the region; the badge sits on its corner until the image is
    // measured (then the badge layout places it in px: badge-layout.util.test.ts).
    expect(article.querySelector('.region-overlay__rect')).toHaveStyle({
      left: '25%',
      top: '50%',
      width: '50%',
      height: '25%',
    });
    expect(buttons[0]).toHaveStyle({ left: '25%', top: '50%' });
    expect(article.querySelector('.region-overlay__dot')).toHaveStyle({ left: '10%', top: '90%' });
    expect(buttons[1]).toHaveStyle({ left: '10%', top: '90%' });

    await userEvent.click(buttons[1] as HTMLElement);

    expect(screen.getByRole('article', { name: 'Comment 2 by Ada Artist' })).toHaveFocus();
    expect(buttons[1]).toHaveAttribute('aria-current', 'true');
    expect(screen.getByRole('button', { name: 'Show region 2 on the image' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByRole('article', { name: 'Comment 2 by Ada Artist' })).toHaveClass(
      'thread-item__card--selected',
    );
  });
});
