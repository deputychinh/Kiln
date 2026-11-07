import { act, render, screen } from '@testing-library/react';

import { useMiddleEllipsis } from '@/hooks/useMiddleEllipsis';

const Name = ({ text }: { text: string }) => {
  const { ref, display } = useMiddleEllipsis(text);
  return <span ref={ref}>{display}</span>;
};

describe('useMiddleEllipsis', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('keeps the text whole where it cannot measure (no ResizeObserver)', () => {
    vi.stubGlobal('ResizeObserver', undefined);

    render(<Name text="sunset_matte_painting_v3_final" />);

    expect(screen.getByText('sunset_matte_painting_v3_final')).toBeInTheDocument();
  });

  it('cuts the text to the element width and follows resizes, then stops observing', () => {
    const observers: { fit: () => void; disconnect: () => void }[] = [];
    vi.stubGlobal(
      'ResizeObserver',
      // A constructor, as the browser's: `new ResizeObserver(fit)`.
      // eslint-disable-next-line prefer-arrow-callback -- arrow functions cannot be constructed
      vi.fn(function ResizeObserverStub(fit: () => void) {
        const observer = { fit, observe: vi.fn(), disconnect: vi.fn() };
        observers.push(observer);
        return observer;
      }),
    );
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
      font: '',
      measureText: (value: string) => ({ width: value.length * 10 }),
    } as unknown as CanvasRenderingContext2D);
    let width = 150;
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(() => width);

    const { unmount } = render(<Name text="sunset_matte_painting_v3_final" />);
    act(() => observers[0]?.fit());
    expect(screen.getByText('sunset_m…_final')).toBeInTheDocument();

    width = 400;
    act(() => observers[0]?.fit());
    expect(screen.getByText('sunset_matte_painting_v3_final')).toBeInTheDocument();

    unmount();
    expect(observers[0]?.disconnect).toHaveBeenCalled();
  });
});
