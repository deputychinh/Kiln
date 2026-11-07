import { parseSignInSearch, safeRedirect } from '@/utils/redirect.util';

describe('safeRedirect', () => {
  it.each(['/assets', '/assets/a1?kind=image#v2', '/settings'])('keeps the app path %s', (path) => {
    expect(safeRedirect(path)).toBe(path);
  });

  it.each([
    undefined,
    42,
    '',
    'assets',
    'https://evil.example/',
    '//evil.example/path',
    '/\\evil.example',
    'javascript:alert(1)',
    '/assets\n/x',
    '/sign-in',
    '/sign-in?redirect=/assets',
  ])('sends %j to the gallery instead', (raw) => {
    expect(safeRedirect(raw)).toBe('/assets');
  });
});

describe('parseSignInSearch', () => {
  it('keeps a string redirect and a true expired flag only', () => {
    expect(parseSignInSearch({ redirect: '/x', expired: true })).toEqual({
      redirect: '/x',
      expired: true,
    });
    expect(parseSignInSearch({ redirect: 3, expired: 'yes' })).toEqual({});
    expect(parseSignInSearch({ expired: 'true' })).toEqual({ expired: true });
  });
});
