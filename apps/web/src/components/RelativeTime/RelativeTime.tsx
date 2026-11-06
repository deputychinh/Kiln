import type { ReactElement } from 'react';

import { useCopy } from '@/hooks/useCopy';
import { formatDateTime, formatRelativeTime } from '@/utils/format.util';

interface RelativeTimeProps {
  iso: string;
}

/** "3 hours ago", with the exact date and time on hover and in `datetime`. */
export const RelativeTime = ({ iso }: RelativeTimeProps): ReactElement => {
  const { locale } = useCopy();
  return (
    <time dateTime={iso} title={formatDateTime(iso, locale)}>
      {formatRelativeTime(iso, locale)}
    </time>
  );
};
