import { act, createEvent, fireEvent, render } from '@testing-library/react';

import { DropOverlay } from '#ui/components/DropOverlay/DropOverlay';

const TARGETS = [
  { id: 'assets', label: 'New assets', hint: 'PNG, JPEG, WebP or .glb' },
  { id: 'version', label: 'New version of rock' },
];

/** A window-level drag event, as the browser sends it while files are dragged over the page. */
const windowDrag = (type: 'dragenter' | 'dragleave' | 'drop' | 'dragend', types = ['Files']) => {
  const event = new Event(type, { bubbles: true, cancelable: true });
  Object.defineProperty(event, 'dataTransfer', { value: { types, files: [] } });
  act(() => {
    window.dispatchEvent(event);
  });
};

/** A drag event on an element of the overlay, carrying files. */
const dragOn = (type: 'dragOver' | 'dragLeave' | 'drop', target: Element, files: File[] = []) => {
  const event = createEvent[type](target);
  Object.defineProperty(event, 'dataTransfer', {
    value: { files, types: ['Files'], dropEffect: 'none' },
  });
  fireEvent(target, event);
  return event;
};

const overlay = (): Element | null => document.querySelector('.drop-overlay');
const target = (id: string): Element => {
  const element = document.querySelector(`[data-drop-target="${id}"]`);
  if (!element) throw new Error(`No drop target ${id}`);
  return element;
};

describe('DropOverlay', () => {
  it('appears only while files are dragged over the window, hidden from assistive technology', () => {
    render(<DropOverlay title="Drop to upload" targets={TARGETS} onDrop={vi.fn()} />);
    expect(overlay()).not.toBeInTheDocument();

    windowDrag('dragenter', ['text/plain']);
    expect(overlay()).not.toBeInTheDocument();

    windowDrag('dragenter');
    expect(overlay()).toHaveAttribute('aria-hidden', 'true');
    expect(overlay()).toHaveTextContent('Drop to upload');
    expect(target('assets')).toHaveTextContent('New assets');
    expect(target('assets')).toHaveTextContent('PNG, JPEG, WebP or .glb');
    expect(target('version')).toHaveTextContent('New version of rock');
  });

  it('stays while the drag crosses elements and goes when it leaves the window', () => {
    render(<DropOverlay title="Drop to upload" targets={TARGETS} onDrop={vi.fn()} />);

    windowDrag('dragenter');
    windowDrag('dragenter');
    windowDrag('dragleave');
    expect(overlay()).toBeInTheDocument();
    windowDrag('dragleave', ['text/plain']);
    expect(overlay()).toBeInTheDocument();

    windowDrag('dragleave');
    expect(overlay()).not.toBeInTheDocument();
  });

  it('highlights the target under the pointer and passes dropped files on with its id', () => {
    const onDrop = vi.fn();
    render(<DropOverlay title="Drop to upload" targets={TARGETS} onDrop={onDrop} />);
    windowDrag('dragenter');

    const over = dragOn('dragOver', target('version'));
    expect(over.defaultPrevented).toBe(true);
    expect(target('version')).toHaveClass('drop-overlay__target--active');
    // Leaving the target, the pointer enters the backdrop: browsers send both events.
    windowDrag('dragenter');
    dragOn('dragLeave', target('version'));
    expect(target('version')).not.toHaveClass('drop-overlay__target--active');

    const file = new File(['x'], 'rock_v2.png', { type: 'image/png' });
    const drop = dragOn('drop', target('version'), [file]);
    windowDrag('drop');

    expect(drop.defaultPrevented).toBe(true);
    expect(onDrop).toHaveBeenCalledWith([file], 'version');
    expect(overlay()).not.toBeInTheDocument();
  });

  it('ignores a drop without files and a drag that carries none', () => {
    const onDrop = vi.fn();
    render(<DropOverlay title="Drop to upload" targets={TARGETS} onDrop={onDrop} />);
    windowDrag('dragenter');

    const text = createEvent.dragOver(target('assets'));
    Object.defineProperty(text, 'dataTransfer', { value: { types: ['text/plain'], files: [] } });
    fireEvent(target('assets'), text);
    dragOn('drop', target('assets'), []);

    expect(text.defaultPrevented).toBe(false);
    expect(onDrop).not.toHaveBeenCalled();
  });

  it('closes when the drag is cancelled', () => {
    render(<DropOverlay title="Drop to upload" targets={TARGETS} onDrop={vi.fn()} />);
    windowDrag('dragenter');

    windowDrag('dragend');

    expect(overlay()).not.toBeInTheDocument();
  });

  it('does nothing while disabled', () => {
    render(
      <DropOverlay title="Drop to upload" targets={TARGETS} onDrop={vi.fn()} isEnabled={false} />,
    );

    windowDrag('dragenter');

    expect(overlay()).not.toBeInTheDocument();
  });
});
