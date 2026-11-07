import { type RefCallback, useCallback, useState } from 'react';

import { middleEllipsis } from '@/utils/ellipsis.util';

let context: CanvasRenderingContext2D | null | undefined;
/** One shared canvas measures text in the element's own font (no layout, no reflow). */
const measurerFor = (element: HTMLElement): ((value: string) => number) | null => {
  context ??= document.createElement('canvas').getContext('2d');
  if (!context) return null;
  const ctx = context;
  const style = getComputedStyle(element);
  ctx.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
  return (value) => ctx.measureText(value).width;
};

/**
 * `text` cut in the middle to fit the element it is shown in, kept up to date as the element
 * resizes (a card in a reflowing grid). Without `ResizeObserver` (tests, old browsers) the text
 * stays whole and CSS clips it.
 */
export const useMiddleEllipsis = (
  text: string,
): { ref: RefCallback<HTMLElement>; display: string } => {
  const [display, setDisplay] = useState(text);
  const ref = useCallback<RefCallback<HTMLElement>>(
    (element) => {
      if (!element || typeof ResizeObserver === 'undefined') return undefined;
      const fit = (): void => {
        const measure = measurerFor(element);
        // Half a pixel of slack: canvas and layout round text widths differently.
        if (measure) setDisplay(middleEllipsis(text, element.clientWidth + 0.5, measure));
      };
      const observer = new ResizeObserver(fit);
      observer.observe(element);
      // Measure again once the web font is in: the first pass may have used the fallback font.
      void document.fonts?.ready.then(fit);
      return () => observer.disconnect();
    },
    [text],
  );
  return { ref, display };
};
