/** Anything newer than this, or dated in the future (clock skew), reads "just now". */
export const JUST_NOW_MS = 45_000;

/** Units for relative times, largest first, with their length in seconds. */
export const RELATIVE_TIME_UNITS: readonly (readonly [Intl.RelativeTimeFormatUnit, number])[] = [
  ['year', 31_536_000],
  ['month', 2_592_000],
  ['week', 604_800],
  ['day', 86_400],
  ['hour', 3_600],
  ['minute', 60],
  ['second', 1],
];

/** SI byte units for `Intl.NumberFormat` (`kilobyte` = 1000 bytes). */
export const BYTE_UNITS = ['byte', 'kilobyte', 'megabyte', 'gigabyte', 'terabyte'] as const;
export const BYTES_PER_UNIT = 1000;
