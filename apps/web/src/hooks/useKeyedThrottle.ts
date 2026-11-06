import { useCallback, useRef } from 'react';

/** Runs `run` at most once per `intervalMs` for each key; extra calls for that key are dropped. */
export const useKeyedThrottle = (intervalMs: number): ((key: string, run: () => void) => void) => {
  const lastRunAtRef = useRef(new Map<string, number>());
  return useCallback(
    (key, run) => {
      const now = Date.now();
      const lastRunAt = lastRunAtRef.current.get(key);
      if (lastRunAt !== undefined && now - lastRunAt < intervalMs) return;
      lastRunAtRef.current.set(key, now);
      run();
    },
    [intervalMs],
  );
};
