let isExpanded = false;
let isReducedMotion = false;

const install = (): void => {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: (query: string): MediaQueryList =>
      ({
        matches:
          (query.includes('min-width: 840px') && isExpanded) ||
          (query.includes('prefers-reduced-motion: reduce') && isReducedMotion),
        media: query,
        onchange: null,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        addListener: () => undefined,
        removeListener: () => undefined,
        dispatchEvent: () => false,
      }) satisfies MediaQueryList,
  });
};

/** Makes `(min-width: 840px)` match or not, as if the window were expanded or compact. */
export const setViewportExpanded = (expanded: boolean): void => {
  isExpanded = expanded;
  isReducedMotion = false;
  install();
};

/** Makes `(prefers-reduced-motion: reduce)` match, as if the person asked for less motion. */
export const setReducedMotion = (reduced: boolean): void => {
  isReducedMotion = reduced;
  install();
};
