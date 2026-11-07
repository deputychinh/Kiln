import { ICON_SIZE, IconButton } from '@kiln/ui';
import { Moon, Sun } from 'lucide-react';
import type { ReactElement } from 'react';

import { Theme } from '@/enums/theme.enum';
import { useCopy } from '@/hooks/useCopy';
import { useTheme } from '@/hooks/useTheme';

/** Switches between the dark and the light theme; the label says what pressing it does. */
export const ThemeToggle = (): ReactElement => {
  const copy = useCopy();
  const { theme, toggle } = useTheme();
  const isDark = theme === Theme.Dark;
  return (
    <IconButton
      label={isDark ? copy.app.themeToLight : copy.app.themeToDark}
      icon={isDark ? <Sun size={ICON_SIZE.md} /> : <Moon size={ICON_SIZE.md} />}
      onClick={toggle}
    />
  );
};
