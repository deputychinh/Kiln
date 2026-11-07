import { apiError } from '@/api/client';
import { TokenAccess } from '@/enums/token-access.enum';
import { initialsOf, isExpired, isSignedOut, scopesFor } from '@/utils/auth.util';

describe('isSignedOut', () => {
  it('is true only for a 401 UNAUTHENTICATED', () => {
    expect(isSignedOut(apiError(401, 'x', 'UNAUTHENTICATED'))).toBe(true);
    expect(isSignedOut(apiError(401, 'x', 'INVALID_CREDENTIALS'))).toBe(false);
    expect(isSignedOut(apiError(403, 'x', 'UNAUTHENTICATED'))).toBe(false);
    expect(isSignedOut(new Error('x'))).toBe(false);
  });
});

describe('initialsOf', () => {
  it.each([
    ['Ada Artist', 'AA'],
    ['  ada  ', 'A'],
    ['Nguyễn Văn An', 'NV'],
    ['', ''],
  ])('%j → %j', (name, initials) => {
    expect(initialsOf(name)).toBe(initials);
  });
});

describe('scopesFor and isExpired', () => {
  it('maps the access choice to API scopes', () => {
    expect(scopesFor(TokenAccess.Read)).toEqual(['read']);
    expect(scopesFor(TokenAccess.ReadWrite)).toEqual(['read', 'write']);
  });

  it('calls a token expired from its expiry instant on', () => {
    const token = { expires_at: '2027-01-01T00:00:00Z' };
    expect(isExpired(token, Date.parse('2026-12-31T23:59:59Z'))).toBe(false);
    expect(isExpired(token, Date.parse('2027-01-01T00:00:00Z'))).toBe(true);
  });
});
