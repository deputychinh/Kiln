/** Why the 3D viewer could not show a model; each has its own message (KILN-9). */
export enum ViewerError {
  /** The download failed or its signed link expired: retrying can help. */
  Download = 'download',
  /** The viewer's own code (the lazily loaded scene) could not be loaded: retrying can help. */
  SceneLoad = 'scene-load',
  /** Larger than the viewer opens, declared or while streaming. */
  TooLarge = 'too-large',
  /** Over the worker's budgets: JSON chunk, vertices, indices or accessor elements. */
  TooComplex = 'too-complex',
  /** Not a glTF 2.0 binary the viewer can read. */
  Unreadable = 'unreadable',
  /** Names a file outside itself; Kiln never fetches it. */
  ExternalReference = 'external-reference',
  /** Needs a decoder the viewer does not ship (Draco, meshopt, Basis). */
  Unsupported = 'unsupported',
  /** The browser could not start or lost WebGL. */
  WebGl = 'webgl',
}
