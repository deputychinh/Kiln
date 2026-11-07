import { formatBytes, formatDateTime, formatRelativeTime, isJustNow } from '@/utils/format.util';

const NOW = Date.parse('2026-11-06T12:00:00Z');

describe('formatRelativeTime', () => {
  it.each([
    ['2026-11-06T12:00:00Z', 'now'],
    ['2026-11-06T11:59:30Z', '30 seconds ago'],
    ['2026-11-06T11:58:00Z', '2 minutes ago'],
    ['2026-11-06T09:00:00Z', '3 hours ago'],
    ['2026-11-05T12:00:00Z', 'yesterday'],
    ['2026-10-23T12:00:00Z', '2 weeks ago'],
    ['2025-11-06T12:00:00Z', 'last year'],
    ['2026-11-06T12:05:00Z', 'in 5 minutes'],
  ])('formats %s as "%s"', (iso, expected) => {
    expect(formatRelativeTime(iso, 'en', NOW)).toBe(expected);
  });

  it('uses the locale', () => {
    expect(formatRelativeTime('2026-11-06T09:00:00Z', 'vi', NOW)).toBe('3 giờ trước');
  });
});

describe('isJustNow', () => {
  const now = Date.parse('2026-11-07T12:00:00Z');

  it.each([
    ['ten seconds ago', '2026-11-07T11:59:50Z', true],
    ['in the future (a server clock ahead)', '2026-11-07T12:05:00Z', true],
    ['a minute ago', '2026-11-07T11:59:00Z', false],
  ])('tells whether a time %s reads as just now', (_case, iso, expected) => {
    expect(isJustNow(iso, now)).toBe(expected);
  });
});

describe('formatDateTime', () => {
  it('gives the date and time in the locale', () => {
    expect(formatDateTime('2026-11-06T12:00:00Z', 'en')).toMatch(/Nov 6, 2026/);
  });
});

describe('formatBytes', () => {
  it.each([
    [0, '0 bytes'],
    [1, '1 byte'],
    [999, '999 bytes'],
    [1000, '1 kB'],
    [1_500_000, '1.5 MB'],
    [500_000_000, '500 MB'],
    [2_000_000_000_000_000, '2,000 TB'],
  ])('formats %i bytes as "%s"', (bytes, expected) => {
    expect(formatBytes(bytes, 'en')).toBe(expected);
  });
});
