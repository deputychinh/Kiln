import { type RefObject, useEffect, useState } from 'react';

/**
 * The element's content size in px, kept current with `ResizeObserver`; null until measured and
 * where it cannot measure (tests, old browsers), so callers keep a size-free layout then.
 */
export const useElementSize = (
  ref: RefObject<HTMLElement | null>,
): { width: number; height: number } | null => {
  const [size, setSize] = useState<{ width: number; height: number } | null>(null);
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return;
      const { width, height } = entry.contentRect;
      setSize((current) =>
        current?.width === width && current.height === height ? current : { width, height },
      );
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);
  return size;
};
