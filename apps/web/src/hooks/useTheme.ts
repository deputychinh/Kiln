import { useState } from 'react';

import { LIGHT_SCHEME_MEDIA_QUERY } from '@/constants/theme.constant';
import { Theme } from '@/enums/theme.enum';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { applyTheme, readStoredTheme } from '@/utils/theme.util';

/** The theme in use (the person's choice, else the system's, else dark) and a switch to the other. */
export const useTheme = (): { theme: Theme; toggle: () => void } => {
  const prefersLight = useMediaQuery(LIGHT_SCHEME_MEDIA_QUERY);
  const [chosen, setChosen] = useState<Theme | null>(readStoredTheme);
  const theme = chosen ?? (prefersLight ? Theme.Light : Theme.Dark);
  const toggle = (): void => {
    const next = theme === Theme.Dark ? Theme.Light : Theme.Dark;
    applyTheme(next);
    setChosen(next);
  };
  return { theme, toggle };
};
