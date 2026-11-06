import { fireEvent, render, screen } from '@testing-library/react';
import { StrictMode } from 'react';

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

  it('falls back when the image had already failed before React listened (cached or invalid)', () => {
    const complete = vi.spyOn(HTMLImageElement.prototype, 'complete', 'get').mockReturnValue(true);
    const onError = vi.fn();

    render(
      <AssetThumb
        src="data:image/png;base64,AAAA"
        alt="Rock"
        placeholder="Image"
        onError={onError}
      />,
    );

    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(screen.getByText('Image')).toBeInTheDocument();
    expect(onError).toHaveBeenCalledExactlyOnceWith('data:image/png;base64,AAAA');
    complete.mockRestore();
  });

  it('keeps an image that is still loading', () => {
    render(<AssetThumb src="https://s3.test/t.webp" alt="Rock" placeholder="Image" />);

    expect(screen.getByRole('img', { name: 'Rock' })).toBeInTheDocument();
  });

  it('reports an already-failed image once under StrictMode (ref callbacks run twice)', () => {
    const complete = vi.spyOn(HTMLImageElement.prototype, 'complete', 'get').mockReturnValue(true);
    const onError = vi.fn();

    render(
      <StrictMode>
        <AssetThumb
          src="data:image/png;base64,AAAA"
          alt="Rock"
          placeholder="Image"
          onError={onError}
        />
      </StrictMode>,
    );

    expect(onError).toHaveBeenCalledTimes(1);
    complete.mockRestore();
  });
});
