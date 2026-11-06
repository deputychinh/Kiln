import { renderHook } from '@testing-library/react';

import { useKeyedThrottle } from '@/hooks/useKeyedThrottle';

describe('useKeyedThrottle', () => {
  afterEach(() => vi.useRealTimers());

  it('runs at most once per interval for each key, independently', () => {
    vi.useFakeTimers({ now: 0 });
    const run = vi.fn();
    const { result } = renderHook(() => useKeyedThrottle(1000));

    result.current('a', run);
    result.current('a', run);
    result.current('b', run);
    vi.setSystemTime(999);
    result.current('a', run);
    expect(run).toHaveBeenCalledTimes(2);

    vi.setSystemTime(1000);
    result.current('a', run);
    expect(run).toHaveBeenCalledTimes(3);
  });
});
