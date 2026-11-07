import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { anAsset, aMe, json, problem } from '@/test/fake-api';
import { renderApp } from '@/test/render-app';
import { routeApi } from '@/test/route-api';

const LIST = '/api/v1/assets?limit=24';
const signedOut = (): Response => problem(401, 'Unauthorized', 'UNAUTHENTICATED');

/** The API with nobody signed in until POST /sessions answers `signIn`. */
const api = (signIn: () => Response) => {
  let me: Response | null = null;
  return routeApi((method, path) => {
    if (path === '/api/v1/me') return me ?? signedOut();
    if (method === 'POST' && path === '/api/v1/sessions') {
      const reply = signIn();
      if (reply.ok) me = json(aMe());
      return reply;
    }
    if (path === LIST) return json({ items: [anAsset()], next_cursor: null });
    return problem(404, 'Not Found', 'NOT_FOUND');
  });
};

const fill = async (email: string, password: string): Promise<void> => {
  if (email) await userEvent.type(screen.getByRole('textbox', { name: 'Email' }), email);
  if (password) await userEvent.type(screen.getByLabelText('Password'), password);
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
};

describe('SignInPage', () => {
  afterEach(() => vi.restoreAllMocks());

  it('sends a signed-out visitor to sign-in, keeping where they were going', async () => {
    api(() => json(aMe(), 201));
    const { router } = renderApp('/assets?kind=image', { me: null });

    expect(await screen.findByRole('heading', { level: 1, name: 'Sign in to Kiln' })).toHaveFocus();
    expect(router.state.location.pathname).toBe('/sign-in');
    expect(router.state.location.search).toEqual({ redirect: '/assets?kind=image' });
    expect(document.title).toBe('Sign in · Kiln');
    expect(screen.queryByRole('banner')).not.toBeInTheDocument(); // no app shell yet
    expect(screen.getByText(/there is no public sign-up/u)).toBeInTheDocument();
  });

  it('signs in and returns to the page that asked for it', async () => {
    const fetchMock = api(() => json(aMe(), 201));
    const { router } = renderApp('/assets?kind=image', { me: null });
    await screen.findByRole('heading', { name: 'Sign in to Kiln' });

    await fill('  Ada@Kiln.test ', 'correct horse battery staple');

    await waitFor(() => expect(router.state.location.pathname).toBe('/assets'));
    expect(router.state.location.search).toMatchObject({ kind: 'image' });
    expect(await screen.findByRole('button', { name: 'Account: Ada Artist' })).toBeInTheDocument();
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST');
    const body = post?.[1]?.body;
    expect(typeof body === 'string' ? JSON.parse(body) : body).toEqual({
      email: 'Ada@Kiln.test',
      password: 'correct horse battery staple',
    });
  });

  it('never follows a return path to another site', async () => {
    api(() => json(aMe(), 201));
    const { router } = renderApp('/sign-in?redirect=%2F%2Fevil.example%2Fx', { me: null });
    await screen.findByRole('heading', { name: 'Sign in to Kiln' });

    await fill('ada@kiln.test', 'correct horse battery staple');

    await waitFor(() => expect(router.state.location.pathname).toBe('/assets'));
  });

  it('checks both fields before sending and moves focus to the first problem', async () => {
    const fetchMock = api(() => json(aMe(), 201));
    renderApp('/sign-in', { me: null });
    await screen.findByRole('heading', { name: 'Sign in to Kiln' });

    await fill('', '');

    const email = screen.getByRole('textbox', { name: 'Email' });
    expect(email).toHaveFocus();
    expect(email).toHaveAccessibleDescription('Enter your email.');
    expect(screen.getByLabelText('Password')).toHaveAccessibleDescription('Enter your password.');
    await userEvent.type(email, 'ada');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(email).toHaveAccessibleDescription('Enter an email address such as name@studio.com.');
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false);
  });

  it.each([
    [problem(401, 'Unauthorized', 'INVALID_CREDENTIALS'), 'The email or password is not correct.'],
    [problem(429, 'Too Many Requests', 'SIGN_IN_THROTTLED'), 'Too many failed attempts.'],
    [problem(403, 'Forbidden', 'CSRF_CHECK_FAILED'), 'Reload the page'],
  ])('says what went wrong, clears the password and focuses it', async (reply, message) => {
    api(() => reply);
    const { router } = renderApp('/sign-in', { me: null });
    await screen.findByRole('heading', { name: 'Sign in to Kiln' });

    await fill('ada@kiln.test', 'wrong password!');

    expect(await screen.findByRole('alert')).toHaveTextContent(message);
    const password = screen.getByLabelText('Password');
    expect(password).toHaveValue('');
    expect(password).toHaveFocus();
    expect(screen.getByRole('textbox', { name: 'Email' })).toHaveValue('ada@kiln.test');
    expect(router.state.location.pathname).toBe('/sign-in');
  });

  it('ignores a second press while signing in', async () => {
    let answer: (reply: Response) => void = () => undefined;
    const fetchMock = routeApi((method, path) =>
      method === 'POST' && path === '/api/v1/sessions'
        ? new Promise<Response>((resolve) => {
            answer = resolve;
          })
        : signedOut(),
    );
    renderApp('/sign-in', { me: null });
    await screen.findByRole('heading', { name: 'Sign in to Kiln' });

    await fill('ada@kiln.test', 'correct horse battery staple');
    const button = screen.getByRole('button', { name: 'Signing in…' });
    expect(button).toHaveAttribute('aria-disabled', 'true');
    await userEvent.click(button);

    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
    answer(problem(401, 'Unauthorized', 'INVALID_CREDENTIALS'));
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument();
  });

  it('sends someone already signed in straight on', async () => {
    routeApi((_, path) => (path === LIST ? json({ items: [], next_cursor: null }) : json(aMe())));
    const { router } = renderApp('/sign-in?redirect=%2Fsettings');

    await waitFor(() => expect(router.state.location.pathname).toBe('/settings'));
  });

  it('brings a person whose session ended back to sign-in with a note, then back to work', async () => {
    let expired = true;
    routeApi((method, path) => {
      if (path === LIST) {
        return expired ? signedOut() : json({ items: [anAsset()], next_cursor: null });
      }
      if (method === 'POST') {
        expired = false;
        return json(aMe(), 201);
      }
      return expired ? signedOut() : json(aMe());
    });
    const { router } = renderApp('/assets');

    expect(await screen.findByText(/Your session ended\./u)).toHaveAttribute('role', 'status');
    expect(router.state.location.pathname).toBe('/sign-in');
    await fill('ada@kiln.test', 'correct horse battery staple');

    await waitFor(() => expect(router.state.location.pathname).toBe('/assets'));
    const gallery = await screen.findByRole('list', { name: 'Assets' });
    expect(await within(gallery).findAllByText('rock_albedo')).not.toHaveLength(0);
  });
});
