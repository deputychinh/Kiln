import type { ComponentType } from 'react';

import type { ViewerError } from '@/enums/viewer-error.enum';
import type { AssetVersion } from '@/interfaces/asset.interface';

/** What the toolbar and the keys ask of the scene; one call is one step. */
export interface ViewerController {
  /** Orbit by whole steps: positive `x` like dragging left, positive `y` like dragging up. */
  rotate: (x: number, y: number) => void;
  /** Move the model on screen by whole steps, like a right-drag: positive `x` right, `y` up. */
  pan: (x: number, y: number) => void;
  /** Positive steps come closer, negative go farther. */
  zoom: (steps: number) => void;
  /** Back to the framed view. */
  reset: () => void;
}

/** The renderer seam: the real scene draws with WebGL, tests pass a fake. */
export interface ModelSceneProps {
  /** The checked .glb bytes. */
  model: ArrayBuffer;
  isReducedMotion: boolean;
  onReady: (controller: ViewerController) => void;
  onError: (error: ViewerError) => void;
}

/** The lazily imported scene module, as `React.lazy` wants it. */
export interface ModelSceneModule {
  default: ComponentType<ModelSceneProps>;
}

export interface ViewerSearch {
  version?: number;
}

/** The version the viewer shows, and whether the URL named something else. */
export interface ViewablePick {
  version: AssetVersion;
  isCorrected: boolean;
}

/** One toolbar button: its name, its glyph and the step it takes. */
export interface ViewerStep {
  label: string;
  glyph: string;
  run: (controller: ViewerController) => void;
}

/** Options for downloading an untrusted model file. */
export interface ModelDownloadOptions {
  /** The size the API recorded for the version. */
  declaredBytes: number;
  maxBytes?: number;
  signal?: AbortSignal;
  onProgress?: (progress: DownloadProgress) => void;
}

/** A model file on its way: downloading, checked and ready, or refused with a reason. */
export type ModelFile =
  | { status: 'loading'; progress: DownloadProgress }
  | { status: 'ready'; model: ArrayBuffer }
  | { status: 'error'; error: ViewerError };

/** Download progress in bytes; `total` is null when neither the server nor the API said. */
export interface DownloadProgress {
  loaded: number;
  total: number | null;
}
