import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useReducer, useRef } from 'react';

import { isApiError } from '@/api/client';
import {
  ASSET_LIST_QUERY_KEY,
  PROCESSING_POLL_MAX_MS,
  PROCESSING_POLL_MS,
} from '@/constants/assets.constant';
import {
  ALREADY_COMPLETE_CODE,
  STORAGE_REJECTED_CODE,
  UPLOAD_CONCURRENCY,
} from '@/constants/upload.constant';
import { UploadStatus } from '@/enums/upload-status.enum';
import { getAsset } from '@/features/assets/services/assets.service';
import {
  completeUpload,
  createAsset,
  sendToStorage,
} from '@/features/uploads/services/uploads.service';
import { useCopy } from '@/hooks/useCopy';
import type { Copy } from '@/interfaces/copy.interface';
import type { UploadItem, UploadQueueState, UploadsApi } from '@/interfaces/upload.interface';
import { describeError } from '@/utils/error.util';
import { declareUpload } from '@/utils/upload-file.util';

const RUNNING = new Set([UploadStatus.Creating, UploadStatus.Uploading, UploadStatus.Completing]);
const FINISHED = new Set([UploadStatus.Ready, UploadStatus.Uploaded]);

const END_STATES = new Set([
  UploadStatus.Ready,
  UploadStatus.Uploaded,
  UploadStatus.Failed,
  UploadStatus.Cancelled,
]);

type Action =
  | { type: 'add'; items: UploadItem[] }
  | { type: 'patch'; id: string; patch: Partial<UploadItem> }
  | { type: 'remove'; id: string };

const endedBetween = (before: UploadItem[], after: UploadItem[]): UploadItem[] => {
  const previous = new Map(before.map((item) => [item.id, item.status]));
  return after.filter(
    (item) => END_STATES.has(item.status) && previous.get(item.id) !== item.status,
  );
};

const nextItems = (items: UploadItem[], action: Action): UploadItem[] => {
  switch (action.type) {
    case 'add':
      return [...items, ...action.items];
    case 'patch':
      return items.map((item) => (item.id === action.id ? { ...item, ...action.patch } : item));
    case 'remove':
      return items.filter((item) => item.id !== action.id);
  }
};

const reducer = (state: UploadQueueState, action: Action): UploadQueueState => {
  const items = nextItems(state.items, action);
  const outcomes = endedBetween(state.items, items);
  return { items, outcomes: outcomes.length > 0 ? outcomes : state.outcomes };
};

const isAbort = (error: unknown): boolean =>
  error instanceof DOMException && error.name === 'AbortError';

const sleep = (ms: number, signal: AbortSignal): Promise<void> =>
  new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener(
      'abort',
      () => {
        clearTimeout(timer);
        reject(new DOMException('Stopped waiting', 'AbortError'));
      },
      { once: true },
    );
  });

const reasonOf = (error: unknown, copy: Copy): string =>
  isApiError(error) && error.code === STORAGE_REJECTED_CODE
    ? copy.uploads.storageRejected
    : describeError(error, copy);

/**
 * The browser upload queue: each file is created through the API (with its own idempotency key,
 * so a retry never makes a second asset), sent to the signed storage form with progress,
 * completed, then watched until its preview is ready — at most `UPLOAD_CONCURRENCY` at a time.
 */
export const useUploads = (): UploadsApi => {
  const copy = useCopy();
  const queryClient = useQueryClient();
  const [{ items, outcomes }, dispatch] = useReducer(reducer, { items: [], outcomes: [] });
  const controllersRef = useRef(new Map<string, AbortController>());

  const patch = useCallback(
    (id: string, change: Partial<UploadItem>) => dispatch({ type: 'patch', id, patch: change }),
    [],
  );
  const refreshGallery = useCallback(
    () => void queryClient.invalidateQueries({ queryKey: ASSET_LIST_QUERY_KEY }),
    [queryClient],
  );

  const waitForPreview = useCallback(
    async ({
      item,
      assetId,
      versionId,
      signal,
    }: {
      item: UploadItem;
      assetId: string;
      versionId: string;
      signal: AbortSignal;
    }) => {
      const deadline = Date.now() + PROCESSING_POLL_MAX_MS;
      while (Date.now() < deadline) {
        await sleep(PROCESSING_POLL_MS, signal);
        const detail = await getAsset(assetId, signal).catch((error: unknown) => {
          if (isAbort(error) || signal.aborted) throw error;
          return null; // a failed poll is retried on the next tick
        });
        const version = detail?.versions.find((candidate) => candidate.id === versionId);
        if (version?.status === 'ready') {
          patch(item.id, { status: UploadStatus.Ready });
          refreshGallery();
          return;
        }
        if (version?.status === 'failed') {
          const reason = version.failure_reason;
          patch(item.id, {
            status: UploadStatus.Failed,
            error: reason ? copy.assets.failure[reason] : copy.errors.unexpected,
            canRetry: false,
          });
          refreshGallery();
          return;
        }
      }
      patch(item.id, { status: UploadStatus.Uploaded });
    },
    [copy, patch, refreshGallery],
  );

  const run = useCallback(
    async (item: UploadItem) => {
      const controller = new AbortController();
      controllersRef.current.set(item.id, controller);
      const { signal } = controller;
      try {
        const { declaration } = declareUpload(item.file);
        if (!declaration) return; // refused files never reach the queue
        patch(item.id, { status: UploadStatus.Creating, progress: 0, error: null });
        const created = await createAsset(declaration, item.idempotencyKey, signal);
        const versionId = created.version.id;
        patch(item.id, { assetId: created.asset.id, versionId });
        if (created.version.status === 'pending_upload' && created.upload) {
          patch(item.id, { status: UploadStatus.Uploading });
          // One update per whole percent: progress events come many times a second.
          let shownPercent = -1;
          await sendToStorage({
            form: created.upload,
            file: item.file,
            onProgress: (progress) => {
              if (Math.floor(progress) === shownPercent) return;
              shownPercent = Math.floor(progress);
              patch(item.id, { progress });
            },
            signal,
          });
          patch(item.id, { status: UploadStatus.Completing, progress: 100 });
          await completeUpload(versionId, signal).catch((error: unknown) => {
            // A retry after a lost reply: the API already took the completion.
            if (!(isApiError(error) && error.code === ALREADY_COMPLETE_CODE)) throw error;
          });
        }
        patch(item.id, { status: UploadStatus.Processing, progress: 100 });
        refreshGallery(); // the new card appears while its preview is made
        await waitForPreview({ item, assetId: created.asset.id, versionId, signal });
      } catch (error) {
        if (signal.aborted || isAbort(error)) patch(item.id, { status: UploadStatus.Cancelled });
        else
          patch(item.id, {
            status: UploadStatus.Failed,
            error: reasonOf(error, copy),
            canRetry: true,
          });
      } finally {
        if (controllersRef.current.get(item.id) === controller)
          controllersRef.current.delete(item.id);
      }
    },
    [copy, patch, refreshGallery, waitForPreview],
  );

  // Start queued files while fewer than the limit are being created, sent or completed.
  useEffect(() => {
    const running = items.filter((item) => RUNNING.has(item.status)).length;
    const next = items
      .filter((item) => item.status === UploadStatus.Queued)
      .slice(0, Math.max(0, UPLOAD_CONCURRENCY - running));
    for (const item of next) {
      patch(item.id, { status: UploadStatus.Creating });
      void run(item);
    }
  }, [items, patch, run]);

  useEffect(() => {
    const controllers = controllersRef.current;
    return () => {
      for (const controller of controllers.values()) controller.abort();
      controllers.clear();
    };
  }, []);

  const add = useCallback(
    (files: File[]) => {
      dispatch({
        type: 'add',
        items: files.map((file) => {
          const { rejection } = declareUpload(file);
          return {
            id: crypto.randomUUID(),
            file,
            status: rejection ? UploadStatus.Failed : UploadStatus.Queued,
            progress: 0,
            error: rejection ? copy.uploads.rejected[rejection] : null,
            canRetry: !rejection,
            idempotencyKey: crypto.randomUUID(),
            assetId: null,
            versionId: null,
          };
        }),
      });
    },
    [copy],
  );

  const cancel = useCallback(
    (id: string) => {
      const controller = controllersRef.current.get(id);
      if (controller) controller.abort();
      else patch(id, { status: UploadStatus.Cancelled });
    },
    [patch],
  );

  const retry = useCallback(
    (id: string) => patch(id, { status: UploadStatus.Queued, progress: 0, error: null }),
    [patch],
  );

  const remove = useCallback((id: string) => {
    controllersRef.current.get(id)?.abort();
    controllersRef.current.delete(id);
    dispatch({ type: 'remove', id });
  }, []);

  return {
    items,
    outcomes,
    summary: {
      finished: items.filter((item) => FINISHED.has(item.status)).length,
      failed: items.filter((item) => item.status === UploadStatus.Failed).length,
      total: items.length,
    },
    add,
    cancel,
    retry,
    remove,
  };
};
