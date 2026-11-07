import { fireEvent, render, screen } from '@testing-library/react';

import { AssetThumb } from '#ui/components/AssetThumb/AssetThumb';

describe('AssetThumb', () => {
  it('renders a lazy image with a fixed intrinsic size', () => {
    render(<AssetThumb src="https://s3.test/t.webp" alt="Rock texture" placeholder="Image" />);

    const image = screen.getByRole('img', { name: 'Rock texture' });
    expect(image).toHaveAttribute('src', 'https://s3.test/t.webp');
    expect(image).toHaveAttribute('loading', 'lazy');
    expect(image).toHaveAttribute('decoding', 'async');
    expect(image).toHaveAttribute('width', '512');
    expect(image).toHaveAttribute('height', '512');
  });

  it('loads eagerly when asked (the hero preview)', () => {
    render(<AssetThumb src="https://s3.test/t.webp" alt="Rock" placeholder="Image" isEager />);

    expect(screen.getByRole('img', { name: 'Rock' })).toHaveAttribute('loading', 'eager');
  });

  it('shows the placeholder when there is no preview', () => {
    render(<AssetThumb src={null} alt="Tree" placeholder="Model" />);

    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(screen.getByText('Model')).toBeInTheDocument();
  });

  it('falls back to the placeholder and reports once when the image fails', () => {
    const onError = vi.fn();
    const { rerender } = render(
      <AssetThumb
        src="https://s3.test/old.webp"
        alt="Rock"
        placeholder="Image"
        onError={onError}
      />,
    );

    fireEvent.error(screen.getByRole('img', { name: 'Rock' }));

    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledWith('https://s3.test/old.webp');
    expect(screen.getByText('Image')).toBeInTheDocument();

    rerender(
      <AssetThumb
        src="https://s3.test/new.webp"
        alt="Rock"
        placeholder="Image"
        onError={onError}
      />,
    );
    expect(screen.getByRole('img', { name: 'Rock' })).toHaveAttribute(
      'src',
      'https://s3.test/new.webp',
    );
  });

  it('sizes the image to its own ratio once loaded, square until then', () => {
    const { container } = render(
      <AssetThumb src="https://s3.test/wide.webp" alt="Wide" placeholder="Image" />,
    );
    const well = container.firstElementChild as HTMLElement;
    expect(well.style.getPropertyValue('--thumb-ratio')).toBe('1');

    const image = screen.getByRole('img', { name: 'Wide' });
    Object.defineProperty(image, 'naturalWidth', { value: 512 });
    Object.defineProperty(image, 'naturalHeight', { value: 256 });
    fireEvent.load(image);

    expect(well.style.getPropertyValue('--thumb-ratio')).toBe('2');
  });
});

describe('AssetThumb overlay', () => {
  const loadAs = (image: HTMLElement, width: number, height: number): void => {
    Object.defineProperty(image, 'naturalWidth', { value: width });
    Object.defineProperty(image, 'naturalHeight', { value: height });
    fireEvent.load(image);
  };

  it('draws the overlay over the image only once it has loaded, in a frame of its ratio', () => {
    const { container } = render(
      <AssetThumb src="/a.png" alt="A" placeholder="Image" overlay={<button>Region 1</button>} />,
    );
    expect(screen.queryByRole('button', { name: 'Region 1' })).not.toBeInTheDocument();

    loadAs(screen.getByRole('img', { name: 'A' }), 800, 400);

    const frame = container.querySelector('.asset-thumb__frame');
    expect(frame).toContainElement(screen.getByRole('img', { name: 'A' }));
    expect(frame).toContainElement(screen.getByRole('button', { name: 'Region 1' }));
    expect(
      container.querySelector<HTMLElement>('.asset-thumb')?.style.getPropertyValue('--thumb-ratio'),
    ).toBe('2');
  });

  it('hides the overlay again while a new image loads, and never shows it on a placeholder', () => {
    const { rerender } = render(
      <AssetThumb src="/a.png" alt="A" placeholder="Image" overlay={<span>Pins</span>} />,
    );
    loadAs(screen.getByRole('img'), 10, 10);
    expect(screen.getByText('Pins')).toBeInTheDocument();

    rerender(<AssetThumb src="/b.png" alt="B" placeholder="Image" overlay={<span>Pins</span>} />);
    expect(screen.queryByText('Pins')).not.toBeInTheDocument();

    rerender(<AssetThumb src={null} alt="" placeholder="Image" overlay={<span>Pins</span>} />);
    expect(screen.queryByText('Pins')).not.toBeInTheDocument();
    expect(screen.getByText('Image')).toBeInTheDocument();
  });

  it('keeps the plain markup without an overlay', () => {
    const { container } = render(<AssetThumb src="/a.png" alt="A" placeholder="Image" />);

    expect(container.querySelector('.asset-thumb__frame')).toBeNull();
  });
});
