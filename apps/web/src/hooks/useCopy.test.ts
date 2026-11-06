import { renderHook } from '@testing-library/react';

import { useCopy } from '@/hooks/useCopy';

const setLanguage = (language: string): void => {
  vi.spyOn(navigator, 'language', 'get').mockReturnValue(language);
};

describe('useCopy', () => {
  afterEach(() => vi.restoreAllMocks());

  it('uses English by default', () => {
    setLanguage('en-US');
    expect(renderHook(() => useCopy()).result.current.assets.retry).toBe('Try again');
  });

  it('uses Vietnamese when the browser prefers it', () => {
    setLanguage('vi-VN');
    expect(renderHook(() => useCopy()).result.current.assets.retry).toBe('Thử lại');
  });
});
