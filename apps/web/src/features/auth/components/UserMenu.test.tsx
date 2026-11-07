import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { aMe, json, problem, urlOf } from '@/test/fake-api';
import { renderApp } from '@/test/render-app';
import { routeApi } from '@/test/route-api';

const LIST = '/api/v1/assets?limit=24';

const api = (signOut: () => Response) => {
  let signedIn = true;
  return routeApi((method, path) => {
    if (method === 'DELETE' && path === '/api/v1/sessions/current') {
      const reply = signOut();
      if (reply.ok) signedIn = false;
      return reply;
    }
    if (!signedIn) return problem(401, 'Unauthorized', 'UNAUTHENTICATED');
    if (path === LIST) return json({ items: [], next_cursor: null });
    if (path === '/api/v1/me/tokens') return json({ items: [] });
    return json(aMe());
  });
};

const openMenu = async (): Promise<HTMLElement> => {
  const trigger = await within(await screen.findByRole('banner')).findByRole('button', {
    name: 'Account: Ada Artist',
  });
  await userEvent.click(trigger);
  return trigger;
};

describe('UserMenu', () => {
  afterEach(() => vi.restoreAllMocks());

  it('shows who is signed in and opens to Settings and Sign out', async () => {
    api(() => new Response(null, { status: 204 }));
    renderApp('/assets');

    const trigger = await openMenu();

    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('ada@kiln.test')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Settings' })).toHaveAttribute('href', '/settings');
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeVisible();
  });

  it('closes on Escape with focus back on the button, and on a click outside', async () => {
    api(() => new Response(null, { status: 204 }));
    renderApp('/assets');
    const trigger = await openMenu();

    await userEvent.keyboard('{Escape}');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(trigger).toHaveFocus();
    expect(screen.queryByRole('button', { name: 'Sign out' })).not.toBeInTheDocument();

    await userEvent.click(trigger);
    await userEvent.click(screen.getByRole('main'));
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  it('closes when focus tabs out of it', async () => {
    api(() => new Response(null, { status: 204 }));
    renderApp('/assets');
    const trigger = await openMenu();

    await userEvent.tab(); // Settings
    await userEvent.tab(); // Sign out
    await userEvent.tab(); // out of the menu

    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  it('opens Settings from the menu', async () => {
    api(() => new Response(null, { status: 204 }));
    const { router } = renderApp('/assets');
    await openMenu();

    await userEvent.click(screen.getByRole('link', { name: 'Settings' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/settings'));
    expect(await screen.findByRole('heading', { level: 1, name: 'Settings' })).toHaveFocus();
    expect(document.title).toBe('Settings · Kiln');
  });

  it('signs out, forgets the session and lands on sign-in', async () => {
    const fetchMock = api(() => new Response(null, { status: 204 }));
    const { router, queryClient } = renderApp('/assets');
    await openMenu();

    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/sign-in'));
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          init?.method === 'DELETE' && urlOf(input).endsWith('/api/v1/sessions/current'),
      ),
    ).toBe(true);
    expect(queryClient.getQueryData(['assets', 'list'])).toBeUndefined();
  });

  it('says so when signing out fails and stays put', async () => {
    api(() => problem(503, 'Service Unavailable', 'DATABASE_UNAVAILABLE'));
    const { router } = renderApp('/assets');
    await openMenu();

    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }));

    expect(await screen.findByText('Could not sign out. Try again.')).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/assets');
  });
});
