import { renderHook } from '@testing-library/react';
import type { FocusEvent } from 'react';

import { useUncoveredFocus } from '@/hooks/useUncoveredFocus';

const at = (element: HTMLElement, top: number, bottom: number): void => {
  element.getBoundingClientRect = () => ({ top, bottom }) as DOMRect;
};

const setUp = (position: string) => {
  const scroller = document.createElement('div');
  scroller.style.overflowY = 'auto';
  const scrollBy = vi.fn();
  scroller.scrollBy = scrollBy;
  const pinned = document.createElement('div');
  pinned.style.position = position;
  const target = document.createElement('button');
  scroller.append(pinned, target);
  document.body.append(scroller);
  at(pinned, 0, 300);
  const { result } = renderHook(() => useUncoveredFocus({ current: pinned }));
  const focus = (top: number): void => {
    at(target, top, top + 24);
    result.current({ target } as unknown as FocusEvent<HTMLElement>);
  };
  return { scrollBy, pinned, focus, cleanUp: () => scroller.remove() };
};

describe('useUncoveredFocus', () => {
  it('scrolls a control focused under the pinned element out from under it', () => {
    const { scrollBy, focus, cleanUp } = setUp('sticky');

    focus(250);

    expect(scrollBy).toHaveBeenCalledWith({ top: -62 });
    cleanUp();
  });

  it('leaves a control below the pinned element where it is', () => {
    const { scrollBy, focus, cleanUp } = setUp('sticky');

    focus(300);

    expect(scrollBy).not.toHaveBeenCalled();
    cleanUp();
  });

  it('does nothing while the element is not pinned (compact screens)', () => {
    const { scrollBy, focus, cleanUp } = setUp('static');

    focus(100);

    expect(scrollBy).not.toHaveBeenCalled();
    cleanUp();
  });
});
