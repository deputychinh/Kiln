import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import type { AccessToken } from '@/interfaces/auth.interface';
import { aToken, json, problem } from '@/test/fake-api';
import { renderApp } from '@/test/render-app';
import { routeApi } from '@/test/route-api';

const TOKENS = '/api/v1/me/tokens';
const SECRET = `kiln_pat_${'x'.repeat(43)}`;

/** A token API over an in-memory list; `fail` makes one verb answer with a problem. */
const tokenApi = (
  initial: AccessToken[],
  fail: { list?: Response; create?: Response; revoke?: Response } = {},
) => {
  let items = [...initial];
  const calls: { method: string; path: string; body: unknown }[] = [];
  const fetchMock = routeApi((method, path, body) => {
    calls.push({ method, path, body });
    if (method === 'GET' && path === TOKENS) return fail.list ?? json({ items });
    if (method === 'POST' && path === TOKENS) {
      if (fail.create) return fail.create;
      const request = body as { name: string; scopes: AccessToken['scopes'] };
      const created = aToken({ id: 'new', name: request.name, scopes: request.scopes });
      items = [created, ...items];
      return json({ ...created, token: SECRET }, 201);
    }
    if (method === 'DELETE' && path.startsWith(`${TOKENS}/`)) {
      if (fail.revoke) return fail.revoke;
      items = items.filter((token) => !path.endsWith(token.id));
      return new Response(null, { status: 204 });
    }
    return problem(404, 'Not Found', 'NOT_FOUND');
  });
  return { calls, fetchMock };
};

const open = async (): Promise<void> => {
  renderApp('/settings');
  await screen.findByRole('heading', { level: 1, name: 'Settings' });
};

describe('SettingsPage tokens', () => {
  afterEach(() => vi.restoreAllMocks());

  it('lists tokens with their prefix, access, dates and an expired mark', async () => {
    tokenApi([
      aToken(),
      aToken({
        id: 'old',
        name: 'Old CLI',
        scopes: ['read'],
        expires_at: '2020-01-01T00:00:00Z',
        last_used_at: '2026-11-05T08:00:00Z',
      }),
    ]);
    await open();

    const list = await screen.findByRole('list', { name: 'Your access tokens' });
    const [first, second] = within(list)
      .getAllByRole('listitem', { name: '' })
      .filter((item) => item.classList.contains('token-list__row'));
    expect(first).toHaveTextContent('Blender laptop');
    expect(first).toHaveTextContent('kiln_pat_Ab3dEf…');
    expect(first).toHaveTextContent('ReadWrite');
    expect(first).toHaveTextContent('Never used');
    expect(first).not.toHaveTextContent('Expired');
    expect(second).toHaveTextContent('Expired');
    expect(within(list).getByRole('button', { name: 'Revoke Old CLI' })).toBeInTheDocument();
  });

  it('shows a loading state, then the empty state with what tokens are for', async () => {
    tokenApi([]);
    await open();

    expect(
      await screen.findByRole('heading', { level: 3, name: 'No access tokens' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/publish from the CLI or Blender/u)).toBeInTheDocument();
  });

  it('shows an error with a retry that loads the list', async () => {
    let failures = 3; // the first try and its two automatic retries
    routeApi((_, path) => {
      if (path !== TOKENS || failures === 0) return json({ items: [aToken()] });
      failures -= 1;
      return problem(503, 'Service Unavailable', 'DATABASE_UNAVAILABLE');
    });
    await open();

    const title = await screen.findByText('Could not load your tokens');
    const alert = title.closest<HTMLElement>('[role="alert"]');
    if (!alert) throw new Error('the error state is an alert');
    await userEvent.click(within(alert).getByRole('button', { name: 'Try again' }));

    expect(await screen.findByText('Blender laptop')).toBeInTheDocument();
  });

  it('asks for a name before creating a token', async () => {
    const { calls } = tokenApi([]);
    await open();

    await userEvent.click(screen.getByRole('button', { name: 'Create token' }));

    const name = screen.getByRole('textbox', { name: 'Name' });
    expect(name).toHaveFocus();
    expect(name).toHaveAccessibleDescription(/Enter a name for the token\./u);
    await userEvent.type(name, 'x'.repeat(81));
    await userEvent.click(screen.getByRole('button', { name: 'Create token' }));
    expect(name).toHaveAccessibleDescription(/80 characters or fewer/u);
    expect(calls.some((call) => call.method === 'POST')).toBe(false);
  });

  it('creates a read-only token, shows it once with copy, then forgets it', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
    const { calls } = tokenApi([]);
    await open();

    await userEvent.type(screen.getByRole('textbox', { name: 'Name' }), '  Render farm ');
    await userEvent.click(screen.getByRole('radio', { name: 'Read only' }));
    await userEvent.click(screen.getByRole('radio', { name: '30 days' }));
    await userEvent.click(screen.getByRole('button', { name: 'Create token' }));

    expect(calls.find((call) => call.method === 'POST')?.body).toEqual({
      name: 'Render farm',
      scopes: ['read'],
      expires_in_days: 30,
    });
    const heading = await screen.findByRole('heading', { name: 'Token “Render farm” created' });
    expect(heading).toHaveFocus();
    expect(screen.getByRole('textbox', { name: 'Your new token' })).toHaveValue(SECRET);
    expect(screen.getByText(/you will not see it again/u)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Copy' }));
    expect(writeText).toHaveBeenCalledWith(SECRET);
    expect(await screen.findByRole('button', { name: 'Copied' })).toBeInTheDocument();
    expect(await screen.findByText('Render farm', { selector: '.token-list__name' })).toBeVisible();

    await userEvent.click(screen.getByRole('button', { name: 'Done' }));

    expect(screen.queryByDisplayValue(SECRET)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create token' })).toBeInTheDocument();
  });

  it('says how to copy by hand when the clipboard refuses', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) },
    });
    tokenApi([]);
    await open();
    await userEvent.type(screen.getByRole('textbox', { name: 'Name' }), 'CLI');
    await userEvent.click(screen.getByRole('button', { name: 'Create token' }));

    await userEvent.click(await screen.findByRole('button', { name: 'Copy' }));

    expect(await screen.findByText(/copy it by hand/u)).toBeInTheDocument();
  });

  it('reports a failed creation and keeps the form', async () => {
    tokenApi([], { create: problem(409, 'Conflict', 'ACCESS_TOKEN_LIMIT') });
    await open();
    await userEvent.type(screen.getByRole('textbox', { name: 'Name' }), 'CLI');

    await userEvent.click(screen.getByRole('button', { name: 'Create token' }));

    expect(await screen.findByText(/Could not create the token: Conflict/u)).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue('CLI');
  });

  it('revokes a token after confirming, and announces it', async () => {
    const { calls } = tokenApi([aToken()]);
    await open();
    const revoke = await screen.findByRole('button', { name: 'Revoke Blender laptop' });

    await userEvent.click(revoke);
    const confirm = screen.getByRole('button', { name: 'Revoke token' });
    expect(confirm).toHaveFocus();
    expect(screen.getByText(/Tools using it stop working at once/u)).toBeInTheDocument();
    await userEvent.click(confirm);

    await waitFor(() => expect(screen.queryByText('Blender laptop')).not.toBeInTheDocument());
    expect(calls.find((call) => call.method === 'DELETE')?.path).toBe(`${TOKENS}/${aToken().id}`);
    expect(screen.getByText('Token “Blender laptop” revoked.')).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'No access tokens' })).toBeInTheDocument();
  });

  it('cancels a revocation with focus back on Revoke', async () => {
    const { calls } = tokenApi([aToken()]);
    await open();
    await userEvent.click(await screen.findByRole('button', { name: 'Revoke Blender laptop' }));

    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(screen.getByRole('button', { name: 'Revoke Blender laptop' })).toHaveFocus();
    expect(calls.some((call) => call.method === 'DELETE')).toBe(false);
  });

  it('reports a failed revocation and keeps the token', async () => {
    tokenApi([aToken()], { revoke: problem(503, 'Service Unavailable', 'DATABASE_UNAVAILABLE') });
    await open();
    await userEvent.click(await screen.findByRole('button', { name: 'Revoke Blender laptop' }));

    await userEvent.click(screen.getByRole('button', { name: 'Revoke token' }));

    expect(await screen.findByText(/Could not revoke the token/u)).toBeInTheDocument();
    expect(screen.getByText('Blender laptop')).toBeInTheDocument();
  });
});
