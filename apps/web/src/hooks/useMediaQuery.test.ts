import { renderHook } from '@testing-library/react';

import { useMediaQuery } from '@/hooks/useMediaQuery';
import { setViewportExpanded } from '@/test/viewport';

describe('useMediaQuery', () => {
  it('reports whether the query matches', () => {
    expect(renderHook(() => useMediaQuery('(min-width: 840px)')).result.current).toBe(false);

    setViewportExpanded(true);
    expect(renderHook(() => useMediaQuery('(min-width: 840px)')).result.current).toBe(true);
  });

  it('subscribes to changes and unsubscribes on unmount', () => {
    const list = window.matchMedia('(min-width: 840px)');
    const add = vi.fn();
    const remove = vi.fn();
    vi.spyOn(window, 'matchMedia').mockReturnValue({
      ...list,
      addEventListener: add,
      removeEventListener: remove,
    });

    const { unmount } = renderHook(() => useMediaQuery('(min-width: 840px)'));
    unmount();

    expect(add).toHaveBeenCalledWith('change', expect.any(Function));
    expect(remove).toHaveBeenCalledWith('change', add.mock.calls[0]?.[1]);
  });
});
