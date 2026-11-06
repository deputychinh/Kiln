import { renderHook } from '@testing-library/react';

import { useThrottledCallback } from '@/hooks/useThrottledCallback';

describe('useThrottledCallback', () => {
  afterEach(() => vi.useRealTimers());

  it('runs at most once per interval', () => {
    vi.useFakeTimers({ now: 0 });
    const callback = vi.fn();
    const { result } = renderHook(() => useThrottledCallback(callback, 1000));

    result.current();
    result.current();
    vi.setSystemTime(999);
    result.current();
    expect(callback).toHaveBeenCalledTimes(1);

    vi.setSystemTime(1000);
    result.current();
    expect(callback).toHaveBeenCalledTimes(2);
  });
});
