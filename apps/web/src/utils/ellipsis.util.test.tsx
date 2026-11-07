import { render } from '@testing-library/react';

import { middleEllipsis, withBreaks } from '@/utils/ellipsis.util';

/** Every character is 10 px wide. */
const measure = (value: string): number => value.length * 10;

describe('middle ellipsis', () => {
  it('keeps a name that fits whole', () => {
    expect(middleEllipsis('rock_albedo', 110, measure)).toBe('rock_albedo');
  });

  it('cuts the middle as one run, keeping a little more head than tail', () => {
    const shown = middleEllipsis('sunset_matte_painting_v3_final', 150, measure);

    expect(shown).toBe('sunset_m…_final');
    expect(measure(shown)).toBeLessThanOrEqual(150);
  });

  it('fills the room it has, one character short of overflowing', () => {
    const name = 'sunset_matte_painting_v3_final';
    const shown = middleEllipsis(name, 200, measure);

    expect(shown).toHaveLength(20);
    expect(middleEllipsis(name, 190, measure)).toHaveLength(19);
  });

  it('shows only the ellipsis when nothing else fits', () => {
    expect(middleEllipsis('rock_albedo', 5, measure)).toBe('…');
  });
});

describe('break opportunities', () => {
  it('lets a name wrap after its separators and keeps its text whole', () => {
    const { container } = render(<h2>{withBreaks('rock_cliff-albedo.v3')}</h2>);

    expect(container.textContent).toBe('rock_cliff-albedo.v3');
    expect(container.querySelectorAll('wbr')).toHaveLength(3);
  });

  it('adds nothing to a name without separators', () => {
    const { container } = render(<h2>{withBreaks('rock')}</h2>);

    expect(container.querySelectorAll('wbr')).toHaveLength(0);
  });
});
