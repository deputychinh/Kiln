import { BYTE_UNITS, BYTES_PER_UNIT, RELATIVE_TIME_UNITS } from '@/constants/time.constant';

/** "3 hours ago", "yesterday", "in 2 minutes" in the given locale. */
export const formatRelativeTime = (iso: string, locale: string, now = Date.now()): string => {
  const seconds = Math.round((Date.parse(iso) - now) / 1000);
  const format = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  const [unit, size] =
    RELATIVE_TIME_UNITS.find(([, length]) => Math.abs(seconds) >= length) ??
    RELATIVE_TIME_UNITS[RELATIVE_TIME_UNITS.length - 1] ??
    (['second', 1] as const);
  return format.format(Math.round(seconds / size), unit);
};

/** Date and time for a tooltip or a detail row, e.g. "6 Nov 2026, 08:30". */
export const formatDateTime = (iso: string, locale: string): string =>
  new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(iso),
  );

/** "1.2 MB" in SI units, one decimal at most. */
export const formatBytes = (bytes: number, locale: string): string => {
  let value = bytes;
  let index = 0;
  while (value >= BYTES_PER_UNIT && index < BYTE_UNITS.length - 1) {
    value /= BYTES_PER_UNIT;
    index += 1;
  }
  return new Intl.NumberFormat(locale, {
    style: 'unit',
    unit: BYTE_UNITS[index],
    // "126 bytes" (long) reads better than "126 byte"; larger units stay short ("1.5 MB").
    unitDisplay: index === 0 ? 'long' : 'short',
    maximumFractionDigits: 1,
  }).format(value);
};
