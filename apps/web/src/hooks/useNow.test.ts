import { act, renderHook } from '@testing-library/react';

import { RELATIVE_TIME_TICK_MS } from '@/constants/assets.constant';
import { useNow } from '@/hooks/useNow';

describe('useNow', () => {
  afterEach(() => vi.useRealTimers());

  it('ticks once a minute with one shared timer and stops when nobody listens', () => {
    vi.useFakeTimers({ now: 0 });
    const spy = vi.spyOn(globalThis, 'setInterval');
    const first = renderHook(() => useNow());
    const second = renderHook(() => useNow());
    expect(first.result.current).toBe(0);
    expect(spy).toHaveBeenCalledTimes(1);

    act(() => {
      vi.advanceTimersByTime(RELATIVE_TIME_TICK_MS);
    });
    expect(first.result.current).toBe(RELATIVE_TIME_TICK_MS);
    expect(second.result.current).toBe(RELATIVE_TIME_TICK_MS);

    first.unmount();
    second.unmount();
    expect(vi.getTimerCount()).toBe(0);

    // A later subscriber starts a fresh timer and sees the current time.
    vi.setSystemTime(5 * RELATIVE_TIME_TICK_MS);
    const third = renderHook(() => useNow());
    expect(third.result.current).toBe(5 * RELATIVE_TIME_TICK_MS);
    act(() => {
      vi.advanceTimersByTime(RELATIVE_TIME_TICK_MS);
    });
    expect(third.result.current).toBe(6 * RELATIVE_TIME_TICK_MS);
    third.unmount();
  });
});
