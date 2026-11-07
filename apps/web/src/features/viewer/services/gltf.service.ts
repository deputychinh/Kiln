import { type Group, LoadingManager } from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

import { ViewerError } from '@/enums/viewer-error.enum';
import { isEmbeddedUrl } from '@/utils/glb.util';
import { viewerErrorOf, viewerFailure } from '@/utils/viewer.util';

/** What a blocked URL becomes: an empty resource, so nothing leaves the browser. */
const BLOCKED_URL = 'data:,';

/**
 * A loading manager that lets only URLs inside the file through (`blob:` images GLTFLoader cuts
 * from the BIN chunk, `data:` URIs) and turns every other one into nothing, telling `onBlocked`.
 */
export const createSafeLoadingManager = (onBlocked: () => void): LoadingManager => {
  const manager = new LoadingManager();
  manager.setURLModifier((url) => {
    if (isEmbeddedUrl(url)) return url;
    onBlocked();
    return BLOCKED_URL;
  });
  return manager;
};

/**
 * Parses checked .glb bytes from memory. Fails with `ExternalReference` the moment the file asks
 * for anything outside itself (the bytes were inspected first; this is the second line), and with
 * `Unreadable` when three cannot read it.
 */
export const parseModel = (buffer: ArrayBuffer): Promise<Group> =>
  new Promise((resolve, reject) => {
    let isBlocked = false;
    const manager = createSafeLoadingManager(() => {
      isBlocked = true;
      reject(viewerFailure(ViewerError.ExternalReference));
    });
    new GLTFLoader(manager).parse(
      buffer,
      '',
      (gltf) => {
        if (isBlocked) return;
        resolve(gltf.scene);
      },
      (error: unknown) => {
        reject(
          isBlocked || viewerErrorOf(error) === ViewerError.ExternalReference
            ? viewerFailure(ViewerError.ExternalReference)
            : viewerFailure(ViewerError.Unreadable),
        );
      },
    );
  });
