import { Button, ButtonVariant, ICON_SIZE, IconButton, IconButtonSize } from '@kiln/ui';
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  ChevronsDown,
  ChevronsUp,
  RotateCcw,
  RotateCw,
  Scan,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
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
  const size = ICON_SIZE.md;
  const groups: { label: string; steps: ViewerStep[] }[] = [
    {
      label: copy.rotate,
      steps: [
        { label: copy.rotateLeft, icon: <RotateCcw size={size} />, run: (c) => c.rotate(1, 0) },
        { label: copy.rotateRight, icon: <RotateCw size={size} />, run: (c) => c.rotate(-1, 0) },
        { label: copy.rotateUp, icon: <ChevronsUp size={size} />, run: (c) => c.rotate(0, 1) },
        { label: copy.rotateDown, icon: <ChevronsDown size={size} />, run: (c) => c.rotate(0, -1) },
      ],
    },
    {
      label: copy.move,
      steps: [
        { label: copy.moveLeft, icon: <ArrowLeft size={size} />, run: (c) => c.pan(-1, 0) },
        { label: copy.moveRight, icon: <ArrowRight size={size} />, run: (c) => c.pan(1, 0) },
        { label: copy.moveUp, icon: <ArrowUp size={size} />, run: (c) => c.pan(0, 1) },
        { label: copy.moveDown, icon: <ArrowDown size={size} />, run: (c) => c.pan(0, -1) },
      ],
    },
    {
      label: copy.zoom,
      steps: [
        { label: copy.zoomIn, icon: <ZoomIn size={size} />, run: (c) => c.zoom(1) },
        { label: copy.zoomOut, icon: <ZoomOut size={size} />, run: (c) => c.zoom(-1) },
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
              <IconButton
                key={step.label}
                variant={ButtonVariant.Secondary}
                size={IconButtonSize.Large}
                label={step.label}
                icon={step.icon}
                disabled={controller === null}
                onClick={() => controller && step.run(controller)}
              />
            ))}
          </div>
        </div>
      ))}
      <Button
        variant={ButtonVariant.Secondary}
        className="viewer-controls__reset"
        icon={<Scan size={ICON_SIZE.sm} />}
        disabled={controller === null}
        onClick={() => controller?.reset()}
      >
        {copy.reset}
      </Button>
    </div>
  );
};
