import { useCallback, useRef } from 'react';

/** Runs `callback` at most once per `intervalMs`; extra calls in between are dropped. */
export const useThrottledCallback = (callback: () => void, intervalMs: number): (() => void) => {
  const lastRunAt = useRef<number | null>(null);
  return useCallback(() => {
    const now = Date.now();
    if (lastRunAt.current !== null && now - lastRunAt.current < intervalMs) return;
    lastRunAt.current = now;
    callback();
  }, [callback, intervalMs]);
};
