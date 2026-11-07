import { Button, ButtonVariant } from '@kiln/ui';
import type { ReactElement } from 'react';

import { useCopy } from '@/hooks/useCopy';
import type { ViewerController, ViewerStep } from '@/interfaces/viewer.interface';

import './ViewerControls.css';

interface ViewerControlsProps {
  /** Null until the model is shown: every control is disabled. */
  controller: ViewerController | null;
}

/** The single-pointer and keyboard alternative to every drag (WCAG 2.5.7): one press, one step. */
export const ViewerControls = ({ controller }: ViewerControlsProps): ReactElement => {
  const copy = useCopy().viewer;
  const groups: { label: string; steps: ViewerStep[] }[] = [
    {
      label: copy.rotate,
      steps: [
        { label: copy.rotateLeft, glyph: '↺', run: (c) => c.rotate(1, 0) },
        { label: copy.rotateRight, glyph: '↻', run: (c) => c.rotate(-1, 0) },
        { label: copy.rotateUp, glyph: '⤒', run: (c) => c.rotate(0, 1) },
        { label: copy.rotateDown, glyph: '⤓', run: (c) => c.rotate(0, -1) },
      ],
    },
    {
      label: copy.move,
      steps: [
        { label: copy.moveLeft, glyph: '←', run: (c) => c.pan(-1, 0) },
        { label: copy.moveRight, glyph: '→', run: (c) => c.pan(1, 0) },
        { label: copy.moveUp, glyph: '↑', run: (c) => c.pan(0, 1) },
        { label: copy.moveDown, glyph: '↓', run: (c) => c.pan(0, -1) },
      ],
    },
    {
      label: copy.zoom,
      steps: [
        { label: copy.zoomIn, glyph: '+', run: (c) => c.zoom(1) },
        { label: copy.zoomOut, glyph: '−', run: (c) => c.zoom(-1) },
      ],
    },
  ];
  return (
    <div className="viewer-controls" role="group" aria-label={copy.controlsLabel}>
      {groups.map((group) => (
        <div
          key={group.label}
          className="viewer-controls__group"
          role="group"
          aria-label={group.label}
        >
          <span className="viewer-controls__label" aria-hidden="true">
            {group.label}
          </span>
          <div className="viewer-controls__buttons">
            {group.steps.map((step) => (
              <Button
                key={step.label}
                variant={ButtonVariant.Secondary}
                className="viewer-controls__button"
                aria-label={step.label}
                title={step.label}
                disabled={controller === null}
                onClick={() => controller && step.run(controller)}
              >
                <span aria-hidden="true">{step.glyph}</span>
              </Button>
            ))}
          </div>
        </div>
      ))}
      <Button
        variant={ButtonVariant.Secondary}
        className="viewer-controls__reset"
        disabled={controller === null}
        onClick={() => controller?.reset()}
      >
        {copy.reset}
      </Button>
    </div>
  );
};
