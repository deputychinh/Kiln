import { THEME_STORAGE_KEY } from '@/constants/theme.constant';
import { Theme } from '@/enums/theme.enum';
import { applyStoredTheme, applyTheme, readStoredTheme } from '@/utils/theme.util';

describe('theme', () => {
  afterEach(() => vi.restoreAllMocks());

  it('reads a stored theme and ignores anything else', () => {
    expect(readStoredTheme()).toBeNull();
    window.localStorage.setItem(THEME_STORAGE_KEY, 'light');
    expect(readStoredTheme()).toBe(Theme.Light);
    window.localStorage.setItem(THEME_STORAGE_KEY, 'sepia');
    expect(readStoredTheme()).toBeNull();
  });

  it('applies a stored theme before the first render, and nothing without one', () => {
    applyStoredTheme();
    expect(document.documentElement.dataset.theme).toBeUndefined();

    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    applyStoredTheme();
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('still switches the page when storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });

    applyTheme(Theme.Light);

    expect(document.documentElement.dataset.theme).toBe('light');
    expect(readStoredTheme()).toBeNull();
  });
});
