import {
  type DragEvent as ReactDragEvent,
  type ReactElement,
  useEffect,
  useRef,
  useState,
} from 'react';
import { createPortal } from 'react-dom';

import type { DropTarget } from '#ui/interfaces/drop-target.interface';

import './DropOverlay.css';

interface DropOverlayProps {
  /** The overlay's heading while files are dragged over the window, e.g. "Drop to upload". */
  title: string;
  /** One or more drop targets; with one, it fills the overlay. */
  targets: DropTarget[];
  /** Called with the dropped files (never empty) and the target they were dropped on. */
  onDrop: (files: File[], targetId: string) => void;
  /** Listen for drags (default); off where uploading makes no sense. */
  isEnabled?: boolean;
}

const carriesFiles = (event: DragEvent | ReactDragEvent): boolean =>
  Array.from(event.dataTransfer?.types ?? []).includes('Files');

/**
 * A whole-window drop target that appears only while files are dragged over the page. It is a
 * pointer shortcut: every drop has a button that opens the file picker (WCAG 2.5.7), so the
 * overlay is hidden from assistive technology.
 */
export const DropOverlay = ({
  title,
  targets,
  onDrop,
  isEnabled = true,
}: DropOverlayProps): ReactElement | null => {
  const [isOpen, setIsOpen] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  // dragenter/dragleave fire for every element crossed: count them to know when the drag left.
  const depthRef = useRef(0);

  useEffect(() => {
    if (!isEnabled) return;
    const close = (): void => {
      depthRef.current = 0;
      setIsOpen(false);
      setActiveId(null);
    };
    const enter = (event: DragEvent): void => {
      if (!carriesFiles(event)) return;
      depthRef.current += 1;
      setIsOpen(true);
    };
    const leave = (event: DragEvent): void => {
      if (!carriesFiles(event)) return;
      depthRef.current = Math.max(0, depthRef.current - 1);
      if (depthRef.current === 0) close();
    };
    window.addEventListener('dragenter', enter);
    window.addEventListener('dragleave', leave);
    window.addEventListener('drop', close);
    window.addEventListener('dragend', close);
    return () => {
      window.removeEventListener('dragenter', enter);
      window.removeEventListener('dragleave', leave);
      window.removeEventListener('drop', close);
      window.removeEventListener('dragend', close);
    };
  }, [isEnabled]);

  if (!isOpen || !isEnabled) return null;
  return createPortal(
    <div className="drop-overlay" aria-hidden="true">
      <p className="drop-overlay__title">{title}</p>
      <div className="drop-overlay__targets">
        {targets.map((target) => (
          // A pointer-only surface (see above): the file buttons are the accessible path.
          <div
            key={target.id}
            className={`drop-overlay__target${activeId === target.id ? ' drop-overlay__target--active' : ''}`}
            data-drop-target={target.id}
            onDragOver={(event) => {
              if (!carriesFiles(event)) return;
              event.preventDefault(); // allows the drop
              event.dataTransfer.dropEffect = 'copy';
              if (activeId !== target.id) setActiveId(target.id);
            }}
            onDragLeave={() => setActiveId(null)}
            onDrop={(event) => {
              event.preventDefault(); // the browser would otherwise open the file
              const files = Array.from(event.dataTransfer?.files ?? []);
              if (files.length > 0) onDrop(files, target.id);
            }}
          >
            {target.icon ? <span className="drop-overlay__icon">{target.icon}</span> : null}
            <span className="drop-overlay__label">{target.label}</span>
            {target.hint ? <span className="drop-overlay__hint">{target.hint}</span> : null}
          </div>
        ))}
      </div>
    </div>,
    document.body,
  );
};
