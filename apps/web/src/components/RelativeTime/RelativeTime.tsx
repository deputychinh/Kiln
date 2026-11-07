import type { ReactElement } from 'react';

import { useCopy } from '@/hooks/useCopy';
import { useNow } from '@/hooks/useNow';
import { formatDateTime, formatRelativeTime, isJustNow } from '@/utils/format.util';

interface RelativeTimeProps {
  iso: string;
}

/** "3 hours ago" (kept current), with the exact date and time on hover and in `datetime`. */
export const RelativeTime = ({ iso }: RelativeTimeProps): ReactElement => {
  const copy = useCopy();
  const { locale } = copy;
  const now = useNow();
  return (
    <time dateTime={iso} title={formatDateTime(iso, locale)}>
      {isJustNow(iso, now) ? copy.app.justNow : formatRelativeTime(iso, locale, now)}
    </time>
  );
};
