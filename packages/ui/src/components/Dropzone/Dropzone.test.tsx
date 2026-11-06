import { createEvent, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Dropzone } from '#ui/components/Dropzone/Dropzone';

const png = (name = 'rock.png'): File => new File(['x'], name, { type: 'image/png' });

const renderDropzone = (onFiles = vi.fn()) => {
  render(
    <Dropzone
      label="Drop images or .glb files here"
      hint="Up to 500 MB each"
      buttonLabel="Choose files"
      accept="image/png,.glb"
      onFiles={onFiles}
    />,
  );
  return { onFiles, zone: screen.getByRole('group', { name: 'Drop images or .glb files here' }) };
};

/** A drag event carrying files, as a browser sends it. */
const dragEvent = (
  type: 'dragEnter' | 'dragOver' | 'dragLeave' | 'drop',
  target: Element,
  files: File[] = [],
) => {
  const event = createEvent[type](target);
  Object.defineProperty(event, 'dataTransfer', {
    value: { files, types: ['Files'], dropEffect: 'none' },
  });
  fireEvent(target, event);
  return event;
};

describe('Dropzone', () => {
  it('names the zone and shows the hint and the file button', () => {
    renderDropzone();

    expect(screen.getByText('Up to 500 MB each')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Choose files' })).toBeInTheDocument();
  });

  it('opens the file picker from the button and passes the chosen files on', async () => {
    const { onFiles } = renderDropzone();
    const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;
    const click = vi.spyOn(input, 'click');

    await userEvent.click(screen.getByRole('button', { name: 'Choose files' }));
    expect(click).toHaveBeenCalledTimes(1);

    await userEvent.upload(input, [png('a.png'), png('b.png')]);
    expect(onFiles).toHaveBeenCalledWith([
      expect.objectContaining({ name: 'a.png' }),
      expect.objectContaining({ name: 'b.png' }),
    ]);
  });

  it('accepts several files of the given types and clears the input so a file can be picked again', async () => {
    const { onFiles } = renderDropzone();
    const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;

    expect(input).toHaveAttribute('accept', 'image/png,.glb');
    expect(input).toHaveAttribute('multiple');
    await userEvent.upload(input, png());
    await userEvent.upload(input, png());

    expect(onFiles).toHaveBeenCalledTimes(2);
    expect(input.value).toBe('');
  });

  it('highlights while files are dragged over it, also across its children', () => {
    const { zone } = renderDropzone();
    const child = screen.getByText('Up to 500 MB each');

    dragEvent('dragEnter', zone);
    dragEvent('dragEnter', child);
    dragEvent('dragLeave', zone);
    expect(zone).toHaveClass('dropzone--active');

    dragEvent('dragLeave', child);
    expect(zone).not.toHaveClass('dropzone--active');
  });

  it('takes dropped files and stops the browser from opening them', () => {
    const { onFiles, zone } = renderDropzone();

    dragEvent('dragEnter', zone);
    const over = dragEvent('dragOver', zone);
    const drop = dragEvent('drop', zone, [png()]);

    expect(over.defaultPrevented).toBe(true);
    expect(drop.defaultPrevented).toBe(true);
    expect(onFiles).toHaveBeenCalledWith([expect.objectContaining({ name: 'rock.png' })]);
    expect(zone).not.toHaveClass('dropzone--active');
  });

  it('ignores a drop without files (text or a link)', () => {
    const { onFiles, zone } = renderDropzone();

    dragEvent('drop', zone, []);

    expect(onFiles).not.toHaveBeenCalled();
  });

  it('ignores drags that carry no files', () => {
    const { zone } = renderDropzone();
    const event = createEvent.dragEnter(zone);
    Object.defineProperty(event, 'dataTransfer', { value: { files: [], types: ['text/plain'] } });
    fireEvent(zone, event);

    expect(zone).not.toHaveClass('dropzone--active');
  });
});
