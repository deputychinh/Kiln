import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { THEME_STORAGE_KEY } from '@/constants/theme.constant';
import { anAsset, fakeApi, json } from '@/test/fake-api';
import { renderApp } from '@/test/render-app';
import { setPrefersLight } from '@/test/viewport';

const LIST = '/api/v1/assets?limit=24';

const renderShell = async () => {
  fakeApi({ [LIST]: [json({ items: [anAsset()], next_cursor: null })] });
  renderApp('/assets');
  await screen.findByRole('heading', { level: 1, name: 'Assets' });
};

describe('AppShell', () => {
  afterEach(() => vi.restoreAllMocks());

  it('has a skip link first, a branded top bar, the main navigation and the main landmark', async () => {
    await renderShell();

    const skip = screen.getByRole('link', { name: 'Skip to content' });
    expect(skip).toHaveAttribute('href', '#main');
    await userEvent.tab();
    expect(skip).toHaveFocus();
    const banner = screen.getByRole('banner');
    expect(within(banner).getByRole('link', { name: 'Kiln' })).toHaveAttribute('href', '/assets');
    const nav = screen.getByRole('navigation', { name: 'Main' });
    expect(within(nav).getByRole('link', { name: 'Assets' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main');
  });

  it('offers a labelled search field that says search is not here yet and never leaves the page', async () => {
    fakeApi({ [LIST]: [json({ items: [], next_cursor: null })] });
    const { router } = renderApp('/assets');
    await screen.findByRole('heading', { level: 1, name: 'Assets' });

    const search = screen.getByRole('searchbox', { name: 'Search assets' });
    expect(search).toHaveAccessibleDescription(
      'Search arrives in a later release. For now, filter the gallery by kind.',
    );
    await userEvent.type(search, 'rock{Enter}');

    expect(router.state.location.pathname).toBe('/assets');
    expect(screen.getByRole('search', { name: 'Search assets' })).toBeInTheDocument();
  });

  it('starts dark, switches to light and remembers the choice', async () => {
    await renderShell();

    await userEvent.click(screen.getByRole('button', { name: 'Switch to light theme' }));

    expect(document.documentElement.dataset.theme).toBe('light');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
    await userEvent.click(screen.getByRole('button', { name: 'Switch to dark theme' }));
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('follows a light system theme until the person chooses', async () => {
    setPrefersLight(true);
    await renderShell();

    expect(screen.getByRole('button', { name: 'Switch to dark theme' })).toBeInTheDocument();
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  it('uses the theme chosen earlier over the system one', async () => {
    setPrefersLight(true);
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    await renderShell();

    expect(screen.getByRole('button', { name: 'Switch to light theme' })).toBeInTheDocument();
  });
});
