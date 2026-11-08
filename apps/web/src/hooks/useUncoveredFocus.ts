import { type FocusEvent, type RefObject, useCallback } from 'react';

/** The room left between a pinned element and whatever focus scrolls up to it. */
const GAP_PX = 12;

const scrollerOf = (element: HTMLElement): HTMLElement | null => {
  let current = element.parentElement;
  while (current) {
    const { overflowY } = getComputedStyle(current);
    if (overflowY === 'auto' || overflowY === 'scroll') return current;
    current = current.parentElement;
  }
  return null;
};

/**
 * A focus handler for content that scrolls under a sticky element (`pinnedRef`): a control that
 * receives focus beneath it — Shift+Tab upward — is scrolled out from under it (WCAG 2.4.11).
 * Does nothing while the element is not sticky (it is only pinned on wide screens).
 */
export const useUncoveredFocus = (
  pinnedRef: RefObject<HTMLElement | null>,
): ((event: FocusEvent<HTMLElement>) => void) =>
  useCallback(
    (event: FocusEvent<HTMLElement>) => {
      const pinned = pinnedRef.current;
      const target = event.target;
      if (!pinned || target === pinned || pinned.contains(target)) return;
      if (getComputedStyle(pinned).position !== 'sticky') return;
      const covered = pinned.getBoundingClientRect().bottom - target.getBoundingClientRect().top;
      if (covered <= 0) return;
      scrollerOf(pinned)?.scrollBy({ top: -(covered + GAP_PX) });
    },
    [pinnedRef],
  );
