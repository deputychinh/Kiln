import { act, render, screen } from '@testing-library/react';
import { type ReactElement, useRef } from 'react';

import { useElementSize } from '@/hooks/useElementSize';

const Probe = (): ReactElement => {
  const ref = useRef<HTMLDivElement>(null);
  const size = useElementSize(ref);
  return <div ref={ref}>{size ? `${String(size.width)}×${String(size.height)}` : 'unknown'}</div>;
};

describe('useElementSize', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('reports the measured size and follows resizes, then stops observing', () => {
    let notify: ResizeObserverCallback = () => undefined;
    const disconnect = vi.fn();
    vi.stubGlobal(
      'ResizeObserver',
      // A constructor, as the browser's: `new ResizeObserver(callback)`.
      // eslint-disable-next-line prefer-arrow-callback -- arrow functions cannot be constructed
      vi.fn(function ResizeObserverStub(callback: ResizeObserverCallback) {
        notify = callback;
        return { observe: vi.fn(), disconnect };
      }),
    );
    const { unmount } = render(<Probe />);
    expect(screen.getByText('unknown')).toBeInTheDocument();

    const resize = (width: number, height: number): void =>
      act(() => {
        notify([{ contentRect: { width, height } } as ResizeObserverEntry], {} as ResizeObserver);
      });
    resize(400, 300);
    expect(screen.getByText('400×300')).toBeInTheDocument();
    resize(200, 150);
    expect(screen.getByText('200×150')).toBeInTheDocument();

    unmount();
    expect(disconnect).toHaveBeenCalled();
  });

  it('stays unknown where it cannot measure', () => {
    vi.stubGlobal('ResizeObserver', undefined);

    render(<Probe />);

    expect(screen.getByText('unknown')).toBeInTheDocument();
  });
});
