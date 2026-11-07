import { useEffect, useEffectEvent, useState } from 'react';

import { downloadModel } from '@/features/viewer/services/model-file.service';
import type { ModelFile } from '@/interfaces/viewer.interface';
import { inspectGlb } from '@/utils/glb.util';
import { viewerErrorOf } from '@/utils/viewer.util';

/**
 * Downloads and inspects a model once per mount: the owner remounts (a `key`) for another file or
 * another attempt, so a re-signed link for the same file never downloads it again. Leaving aborts.
 */
export const useModelFile = (url: string, declaredBytes: number): ModelFile => {
  const [file, setFile] = useState<ModelFile>({
    status: 'loading',
    progress: { loaded: 0, total: declaredBytes },
  });
  // The newest signed link when the download starts, without restarting it when the link changes.
  const startUrl = useEffectEvent(() => url);
  const startSize = useEffectEvent(() => declaredBytes);

  useEffect(() => {
    const controller = new AbortController();
    downloadModel(startUrl(), {
      declaredBytes: startSize(),
      signal: controller.signal,
      onProgress: (progress) => setFile({ status: 'loading', progress }),
    }).then(
      (model) => {
        const error = inspectGlb(model);
        setFile(error === null ? { status: 'ready', model } : { status: 'error', error });
      },
      (error: unknown) => {
        if (!controller.signal.aborted) setFile({ status: 'error', error: viewerErrorOf(error) });
      },
    );
    return () => controller.abort();
  }, []);

  return file;
};
