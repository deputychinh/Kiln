let isExpanded = false;
let isLarge = false;
let isReducedMotion = false;
let prefersLight = false;

const install = (): void => {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: (query: string): MediaQueryList =>
      ({
        matches:
          (query.includes('min-width: 840px') && isExpanded) ||
          (query.includes('min-width: 1200px') && isLarge) ||
          (query.includes('prefers-reduced-motion: reduce') && isReducedMotion) ||
          (query.includes('prefers-color-scheme: light') && prefersLight),
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
  isLarge = false;
  isReducedMotion = false;
  prefersLight = false;
  install();
};

/** Makes `(prefers-reduced-motion: reduce)` match, as if the person asked for less motion. */
export const setReducedMotion = (reduced: boolean): void => {
  isReducedMotion = reduced;
  install();
};

/** Makes `(prefers-color-scheme: light)` match, as if the system used a light theme. */
export const setPrefersLight = (light: boolean): void => {
  prefersLight = light;
  install();
};

/** Makes `(min-width: 1200px)` (and so the expanded class) match, as on a large window. */
export const setViewportLarge = (large: boolean): void => {
  isLarge = large;
  isExpanded = large || isExpanded;
  install();
};
