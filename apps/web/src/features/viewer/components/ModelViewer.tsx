import { AssetThumb, Button, ButtonVariant, ProgressBar } from '@kiln/ui';
import {
  type KeyboardEvent,
  type ReactElement,
  type ReactNode,
  useCallback,
  useId,
  useState,
} from 'react';

import { REDUCED_MOTION_QUERY, RETRYABLE_VIEWER_ERRORS } from '@/constants/viewer.constant';
import type { ViewerError } from '@/enums/viewer-error.enum';
import { SceneBoundary } from '@/features/viewer/components/SceneBoundary';
import { ViewerControls } from '@/features/viewer/components/ViewerControls';
import { useModelFile } from '@/features/viewer/hooks/useModelFile';
import { useSceneModule } from '@/features/viewer/hooks/useSceneModule';
import { useCopy } from '@/hooks/useCopy';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import type { ModelSceneModule, ViewerController } from '@/interfaces/viewer.interface';
import { formatBytes } from '@/utils/format.util';
import { withoutQuery } from '@/utils/signed-url.util';

import './ModelViewer.css';

/** three.js and the scene load only when a model is shown (their own chunk). */
const loadModelScene = (): Promise<ModelSceneModule> =>
  import('@/features/viewer/components/ModelScene').then((module) => ({
    default: module.ModelScene,
  }));

interface ModelViewerProps {
  /** The version's signed `download_url`. */
  fileUrl: string;
  sizeBytes: number;
  versionNumber: number;
  previewUrl: string | null;
  onPreviewError: (src: string) => void;
  /** Fetches fresh signed links; a retry starts once it settles. */
  onRetry: () => Promise<unknown>;
  /** Loads the renderer; tests pass a fake because jsdom has no WebGL. */
  loadScene?: () => Promise<ModelSceneModule>;
  /** Shown under the controls (facts about the version). */
  children?: ReactNode;
}

type SceneState = { status: 'preparing' } | { status: 'ready'; controller: ViewerController };

/** Keys on the focused stage → one step, the same as the buttons and a drag in that direction. */
const stepFor = (event: KeyboardEvent): ((controller: ViewerController) => void) | null => {
  if (event.ctrlKey || event.metaKey || event.altKey) return null;
  // The arrow's direction on screen; Shift moves the model that way instead of turning it.
  const x = { ArrowLeft: -1, ArrowRight: 1 }[event.key] ?? 0;
  const y = { ArrowUp: 1, ArrowDown: -1 }[event.key] ?? 0;
  if (x !== 0 || y !== 0) {
    return event.shiftKey ? (c) => c.pan(x, y) : (c) => c.rotate(x === 0 ? 0 : -x, y);
  }
  if (event.key === '+' || event.key === '=') return (c) => c.zoom(1);
  if (event.key === '-' || event.key === '_') return (c) => c.zoom(-1);
  if (event.key === '0' || event.key === 'Home') return (c) => c.reset();
  return null;
};

const ModelStage = ({
  fileUrl,
  sizeBytes,
  versionNumber,
  previewUrl,
  onPreviewError,
  onRetry,
  loadScene = loadModelScene,
  children,
}: Omit<ModelViewerProps, 'onRetry'> & { onRetry: () => void }): ReactElement => {
  const copy = useCopy();
  const keysId = useId();
  const file = useModelFile(fileUrl, sizeBytes);
  const [scene, setScene] = useState<SceneState>({ status: 'preparing' });
  const [sceneError, setSceneError] = useState<ViewerError | null>(null);
  // The first reason stays: a lost context after a parse error is not the news.
  const onSceneError = useCallback(
    (next: ViewerError) => setSceneError((current) => current ?? next),
    [],
  );
  // The scene module's own `ModelScene` export, held in state: one identity for the whole mount.
  // eslint-disable-next-line @eslint-react/static-components -- loaded, not created, in render
  const Scene = useSceneModule(loadScene, onSceneError);
  const isReducedMotion = useMediaQuery(REDUCED_MOTION_QUERY);
  const onReady = useCallback(
    (controller: ViewerController) => setScene({ status: 'ready', controller }),
    [],
  );

  const error = file.status === 'error' ? file.error : sceneError;
  const controller = error === null && scene.status === 'ready' ? scene.controller : null;
  const label = copy.viewer.stageLabel(versionNumber);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>): void => {
    const step = controller ? stepFor(event) : null;
    if (!step || !controller) return;
    event.preventDefault(); // arrows and Home would scroll the page
    step(controller);
  };

  let status: ReactNode = null;
  if (error === null && file.status === 'loading') {
    const { loaded, total } = file.progress;
    status = (
      <ProgressBar
        label={copy.viewer.downloading(versionNumber)}
        value={total ? (loaded / total) * 100 : 0}
        valueText={copy.viewer.progress(
          formatBytes(loaded, copy.locale),
          formatBytes(total ?? sizeBytes, copy.locale),
        )}
      />
    );
  } else if (error === null && controller === null) {
    status = <p className="model-viewer__preparing">{copy.viewer.preparing}</p>;
  }

  return (
    <div className="model-viewer">
      {/* Above the stage, so the reason is seen before the fallback, on every size. */}
      {error ? (
        <div className="model-viewer__error" role="alert">
          <p className="model-viewer__message">{copy.viewer.errors[error]}</p>
          <p className="model-viewer__fallback">{copy.viewer.fallback}</p>
          {RETRYABLE_VIEWER_ERRORS.has(error) ? (
            <Button variant={ButtonVariant.Secondary} onClick={onRetry}>
              {copy.viewer.retry}
            </Button>
          ) : null}
        </div>
      ) : null}
      {/* eslint-disable-next-line jsx-a11y-x/no-noninteractive-element-interactions -- a 3D stage is an application (WAI-ARIA): screen readers pass the arrow keys through to it */}
      <div
        className={`model-viewer__stage${controller ? ' model-viewer__stage--ready' : ''}`}
        role="application"
        aria-label={label}
        aria-describedby={keysId}
        // eslint-disable-next-line jsx-a11y-x/no-noninteractive-tabindex -- the stage takes the keys, so keyboard users must reach it (WCAG 2.1.1)
        tabIndex={controller ? 0 : -1}
        onKeyDown={onKeyDown}
      >
        {file.status === 'ready' && sceneError === null && Scene ? (
          <div className="model-viewer__canvas">
            <SceneBoundary onError={onSceneError}>
              {/* eslint-disable-next-line react-hooks/static-components, @eslint-react/static-components -- a module export kept in state (useSceneModule), not a component made in render */}
              <Scene
                model={file.model}
                isReducedMotion={isReducedMotion}
                onReady={onReady}
                onError={onSceneError}
              />
            </SceneBoundary>
          </div>
        ) : null}
        {controller ? null : (
          <div className={`model-viewer__poster${error ? '' : ' model-viewer__poster--dimmed'}`}>
            <div className="model-viewer__still">
              <AssetThumb
                src={previewUrl}
                alt={copy.viewer.previewAlt(versionNumber)}
                placeholder={copy.viewer.noPreview}
                onError={onPreviewError}
                isEager
              />
            </div>
          </div>
        )}
        {status ? (
          <div className="model-viewer__status" role="status">
            {status}
          </div>
        ) : null}
      </div>
      <div className="model-viewer__panel">
        <ViewerControls controller={controller} />
        <section className="model-viewer__keys" aria-label={copy.viewer.keysTitle}>
          <p id={keysId} className="model-viewer__hint">
            {copy.viewer.keys}
          </p>
          <p className="model-viewer__hint">{copy.viewer.pointer}</p>
        </section>
        {children}
      </div>
    </div>
  );
};

/**
 * A model version in 3D: download with progress, a checked file, then an orbiting scene with
 * buttons and keys for every gesture. Any failure shows why, over the still preview.
 */
export const ModelViewer = ({ onRetry, ...props }: ModelViewerProps): ReactElement => {
  const [attempt, setAttempt] = useState(0);
  const retry = (): void => {
    void onRetry().finally(() => setAttempt((count) => count + 1));
  };
  // One mount per file and attempt: a re-signed link for the same file keeps what was loaded.
  return (
    <ModelStage
      key={`${withoutQuery(props.fileUrl)}#${String(attempt)}`}
      {...props}
      onRetry={retry}
    />
  );
};
