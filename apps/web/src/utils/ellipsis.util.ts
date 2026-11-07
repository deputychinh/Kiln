import { createElement, Fragment, type ReactNode } from 'react';

const ELLIPSIS = '…';
/** The share of kept characters before the ellipsis: a little more head than tail. */
const HEAD_SHARE = 0.55;

/**
 * The longest "head…tail" form of `text` that `measure` says fits in `maxWidth`, as one string,
 * so the ellipsis sits between the two parts with the font's own spacing. The whole text when it
 * fits; just the ellipsis when nothing else does.
 */
export const middleEllipsis = (
  text: string,
  maxWidth: number,
  measure: (value: string) => number,
): string => {
  if (measure(text) <= maxWidth) return text;
  const cut = (kept: number): string => {
    const head = Math.ceil(kept * HEAD_SHARE);
    return `${text.slice(0, head)}${ELLIPSIS}${text.slice(text.length - (kept - head))}`;
  };
  let low = 0;
  let high = text.length - 1;
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    if (measure(cut(middle)) <= maxWidth) low = middle;
    else high = middle - 1;
  }
  return cut(low);
};

/** Characters after which a long name may wrap (`snake_case`, `kebab-case`, `v3.final`). */
const BREAK_AFTER = /([_\-./])/;

/**
 * A name with line-break opportunities after its separators, so a two-line title wraps between
 * the parts of `rock_cliff_albedo_v3` instead of in the middle of a word.
 */
export const withBreaks = (name: string): ReactNode =>
  createElement(
    Fragment,
    null,
    ...name
      .split(BREAK_AFTER)
      .flatMap((part, index) =>
        BREAK_AFTER.test(part)
          ? [part, createElement('wbr', { key: `b${String(index)}` })]
          : [part],
      ),
  );
