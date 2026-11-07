import { THEME_STORAGE_KEY } from '@/constants/theme.constant';
import { Theme } from '@/enums/theme.enum';

const isTheme = (value: unknown): value is Theme => Object.values(Theme).includes(value as Theme);

/** The theme the person chose earlier, or null to follow the system (storage may be blocked). */
export const readStoredTheme = (): Theme | null => {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isTheme(stored) ? stored : null;
  } catch {
    return null;
  }
};

/** Applies a theme to the page (`data-theme` drives the tokens) and remembers it when it can. */
export const applyTheme = (theme: Theme): void => {
  document.documentElement.dataset.theme = theme;
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Storage blocked (private mode, policy): the choice holds for this page only.
  }
};

/** Before the first render: a stored choice wins over the system's, so the page never flips. */
export const applyStoredTheme = (): void => {
  const stored = readStoredTheme();
  if (stored) document.documentElement.dataset.theme = stored;
};
