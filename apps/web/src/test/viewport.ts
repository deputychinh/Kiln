let isExpanded = false;

/** Makes `(min-width: 840px)` match or not, as if the window were expanded or compact. */
export const setViewportExpanded = (expanded: boolean): void => {
  isExpanded = expanded;
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: (query: string): MediaQueryList =>
      ({
        matches: query.includes('min-width: 840px') ? isExpanded : false,
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
