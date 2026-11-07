import { type ComponentType, useEffect, useEffectEvent, useState } from 'react';

import { ViewerError } from '@/enums/viewer-error.enum';
import type { ModelSceneModule, ModelSceneProps } from '@/interfaces/viewer.interface';

/**
 * Loads the scene's code (three.js, its own chunk) once per mount, alongside the model download.
 * A failed import reports `SceneLoad`; the retry is a new mount, which imports again.
 */
export const useSceneModule = (
  load: () => Promise<ModelSceneModule>,
  onError: (error: ViewerError) => void,
): ComponentType<ModelSceneProps> | null => {
  const [scene, setScene] = useState<ComponentType<ModelSceneProps> | null>(null);
  const startLoad = useEffectEvent(load);
  const fail = useEffectEvent(() => onError(ViewerError.SceneLoad));

  useEffect(() => {
    let isCurrent = true;
    startLoad().then(
      (module) => {
        if (isCurrent) setScene(() => module.default);
      },
      () => {
        if (isCurrent) fail();
      },
    );
    return () => {
      isCurrent = false;
    };
  }, []);

  return scene;
};
