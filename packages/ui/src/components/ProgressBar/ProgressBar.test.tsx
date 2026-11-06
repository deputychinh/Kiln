import { render, screen } from '@testing-library/react';

import { ProgressBar } from '#ui/components/ProgressBar/ProgressBar';

describe('ProgressBar', () => {
  it('exposes its name and value to assistive technology', () => {
    render(<ProgressBar label="Uploading rock.png" value={42} />);

    const bar = screen.getByRole('progressbar', { name: 'Uploading rock.png' });
    expect(bar).toHaveAttribute('aria-valuemin', '0');
    expect(bar).toHaveAttribute('aria-valuemax', '100');
    expect(bar).toHaveAttribute('aria-valuenow', '42');
  });

  it.each([
    [-5, '0'],
    [140, '100'],
    [33.6, '34'],
    [Number.NaN, '0'],
  ])('keeps %s inside 0–100 as a whole percent (%s)', (value, expected) => {
    render(<ProgressBar label="Upload" value={value} />);

    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', expected);
  });

  it('fills to the value', () => {
    render(<ProgressBar label="Upload" value={25} />);

    expect(screen.getByRole('progressbar').firstElementChild).toHaveStyle({ inlineSize: '25%' });
  });

  it('can carry a readable value text', () => {
    render(<ProgressBar label="Upload" value={10} valueText="10 %, 1 of 10 MB" />);

    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuetext', '10 %, 1 of 10 MB');
  });
});
