import { render } from '@testing-library/react';

import { Skeleton } from '#ui/components/Skeleton/Skeleton';
import { SkeletonShape } from '#ui/enums/skeleton-shape.enum';

describe('Skeleton', () => {
  it('is hidden from assistive technology and takes the shape modifier', () => {
    const { container } = render(<Skeleton shape={SkeletonShape.Tile} />);

    const block = container.firstElementChild;
    expect(block).toHaveAttribute('aria-hidden', 'true');
    expect(block).toHaveClass('skeleton', 'skeleton--tile');
  });

  it('is a text line by default', () => {
    const { container } = render(<Skeleton />);

    expect(container.firstElementChild).toHaveClass('skeleton--line');
  });
});
