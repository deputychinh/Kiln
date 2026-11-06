import { useSyncExternalStore } from 'react';

import { RELATIVE_TIME_TICK_MS } from '@/constants/assets.constant';

const listeners = new Set<() => void>();
let now = Date.now();
let timer: ReturnType<typeof setInterval> | null = null;

const subscribe = (listener: () => void): (() => void) => {
  listeners.add(listener);
  if (timer === null) {
    now = Date.now();
    timer = setInterval(() => {
      now = Date.now();
      listeners.forEach((notify) => notify());
    }, RELATIVE_TIME_TICK_MS);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  };
};

/** The current time, updated once a minute by one shared timer for every subscriber. */
export const useNow = (): number => useSyncExternalStore(subscribe, () => now);
