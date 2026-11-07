import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createRef } from 'react';

import { FilePickerButton } from '#ui/components/FilePickerButton/FilePickerButton';
import { ButtonVariant } from '#ui/enums/button-variant.enum';

const png = (name = 'rock.png'): File => new File(['x'], name, { type: 'image/png' });

const inputOf = (button: HTMLElement): HTMLInputElement => {
  const input = button.parentElement?.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error('The picker has no file input');
  return input;
};

describe('FilePickerButton', () => {
  it('opens the file picker from the button and passes the picked files on', async () => {
    const onFiles = vi.fn();
    render(
      <FilePickerButton accept="image/png,.glb" onFiles={onFiles}>
        Upload
      </FilePickerButton>,
    );
    const button = screen.getByRole('button', { name: 'Upload' });
    const input = inputOf(button);
    const click = vi.spyOn(input, 'click');

    await userEvent.click(button);
    expect(click).toHaveBeenCalledTimes(1);
    expect(button).toHaveClass('button--primary');
    expect(input).toHaveAttribute('accept', 'image/png,.glb');
    expect(input).toHaveAttribute('multiple');

    await userEvent.upload(input, [png('a.png'), png('b.png')]);
    expect(onFiles).toHaveBeenCalledWith([
      expect.objectContaining({ name: 'a.png' }),
      expect.objectContaining({ name: 'b.png' }),
    ]);
  });

  it('clears the input so the same file can be picked again, and ignores an empty pick', async () => {
    const onFiles = vi.fn();
    render(<FilePickerButton onFiles={onFiles}>Upload</FilePickerButton>);
    const input = inputOf(screen.getByRole('button', { name: 'Upload' }));

    await userEvent.upload(input, png());
    await userEvent.upload(input, png());
    fireEvent.change(input, { target: { files: [] } });

    expect(onFiles).toHaveBeenCalledTimes(2);
    expect(input.value).toBe('');
  });

  it('takes one file, a fuller accessible name, a variant and a ref', () => {
    const ref = createRef<HTMLButtonElement>();
    render(
      <FilePickerButton
        ref={ref}
        isMultiple={false}
        accessibleName="Upload a new version of rock"
        variant={ButtonVariant.Secondary}
        onFiles={vi.fn()}
      >
        Upload
      </FilePickerButton>,
    );

    const button = screen.getByRole('button', { name: 'Upload a new version of rock' });
    expect(ref.current).toBe(button);
    expect(button).toHaveClass('button--secondary');
    expect(inputOf(button)).not.toHaveAttribute('multiple');
  });
});
