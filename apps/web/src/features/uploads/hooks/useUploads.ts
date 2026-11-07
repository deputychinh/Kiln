import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useReducer, useRef } from 'react';

import { isApiError } from '@/api/client';
import {
  ASSET_LIST_QUERY_KEY,
  assetDetailQueryKey,
  PROCESSING_POLL_MAX_MS,
  PROCESSING_POLL_MS,
} from '@/constants/assets.constant';
import { ALREADY_COMPLETE_CODE, UPLOAD_CONCURRENCY } from '@/constants/upload.constant';
import { UploadStatus } from '@/enums/upload-status.enum';
import { getAsset } from '@/features/assets/services/assets.service';
import {
  addVersion,
  completeUpload,
  createAsset,
  sendToStorage,
} from '@/features/uploads/services/uploads.service';
import { useCopy } from '@/hooks/useCopy';
import type {
  UploadItem,
  UploadQueueState,
  UploadsApi,
  UploadTarget,
} from '@/interfaces/upload.interface';
import { uploadFailureOf } from '@/utils/upload-error.util';
import { declareUpload } from '@/utils/upload-file.util';

/** Recent outcomes kept for announcements; older ones have long been read out. */
const OUTCOMES_KEPT = 50;
const RUNNING = new Set([UploadStatus.Creating, UploadStatus.Uploading, UploadStatus.Completing]);

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
  const ended = endedBetween(state.items, items);
  if (ended.length === 0) return { ...state, items };
  // Append, never replace: outcomes from separate changes in one frame must all be heard.
  return {
    items,
    outcomes: [...state.outcomes, ...ended].slice(-OUTCOMES_KEPT),
    outcomeCount: state.outcomeCount + ended.length,
  };
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

/**
 * Queued rows to start now, in order: at most `UPLOAD_CONCURRENCY` running in all, and never two
 * for the same asset, so new versions of one asset are numbered in the order they were added.
 */
const nextToStart = (items: UploadItem[]): UploadItem[] => {
  const running = items.filter((item) => RUNNING.has(item.status));
  const busyAssets = new Set(running.map((item) => item.targetAssetId).filter(Boolean));
  const picked: UploadItem[] = [];
  for (const item of items) {
    if (running.length + picked.length >= UPLOAD_CONCURRENCY) break;
    if (item.status !== UploadStatus.Queued) continue;
    if (item.targetAssetId !== null) {
      if (busyAssets.has(item.targetAssetId)) continue;
      busyAssets.add(item.targetAssetId);
    }
    picked.push(item);
  }
  return picked;
};

/**
 * The browser upload queue for the whole assets page: each file becomes a new asset, or a new
 * version of a target asset, through the API (with its own idempotency key, so a retry never
 * makes a second one), is sent to the signed storage form with progress, completed, then watched
 * until its preview is ready.
 */
export const useUploads = (): UploadsApi => {
  const copy = useCopy();
  const queryClient = useQueryClient();
  const [{ items, outcomes, outcomeCount }, dispatch] = useReducer(reducer, {
    items: [],
    outcomes: [],
    outcomeCount: 0,
  });
  const controllersRef = useRef(new Map<string, AbortController>());

  const patch = useCallback(
    (id: string, change: Partial<UploadItem>) => dispatch({ type: 'patch', id, patch: change }),
    [],
  );
  const refreshGallery = useCallback(
    () => void queryClient.invalidateQueries({ queryKey: ASSET_LIST_QUERY_KEY }),
    [queryClient],
  );
  /** The detail of the asset a version was added to; new assets have no open detail to refresh. */
  const refreshTarget = useCallback(
    (item: UploadItem) => {
      if (item.targetAssetId === null) return;
      void queryClient.invalidateQueries({ queryKey: assetDetailQueryKey(item.targetAssetId) });
    },
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
          refreshTarget(item);
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
          refreshTarget(item);
          return;
        }
      }
      patch(item.id, { status: UploadStatus.Uploaded });
    },
    [copy, patch, refreshGallery, refreshTarget],
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
        const created =
          item.targetAssetId === null
            ? await createAsset(declaration, item.idempotencyKey, signal)
            : await addVersion({
                assetId: item.targetAssetId,
                declaration,
                idempotencyKey: item.idempotencyKey,
                signal,
              });
        const versionId = created.version.id;
        patch(item.id, { assetId: created.asset.id, versionId });
        refreshTarget(item); // the new version shows in the open detail at once
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
            ...uploadFailureOf(error, copy, item.targetKind),
          });
      } finally {
        if (controllersRef.current.get(item.id) === controller)
          controllersRef.current.delete(item.id);
      }
    },
    [copy, patch, refreshGallery, refreshTarget, waitForPreview],
  );

  // Start queued files while fewer than the limit are being created, sent or completed.
  useEffect(() => {
    for (const item of nextToStart(items)) {
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
    (files: File[], target?: UploadTarget) => {
      dispatch({
        type: 'add',
        items: files.map((file) => {
          const { rejection } = declareUpload(file, target?.kind);
          return {
            id: crypto.randomUUID(),
            file,
            status: rejection ? UploadStatus.Failed : UploadStatus.Queued,
            progress: 0,
            error: rejection ? copy.uploads.rejected[rejection] : null,
            canRetry: !rejection,
            idempotencyKey: crypto.randomUUID(),
            assetId: target?.assetId ?? null,
            versionId: null,
            targetAssetId: target?.assetId ?? null,
            targetKind: target?.kind ?? null,
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
    outcomeCount,
    add,
    cancel,
    retry,
    remove,
  };
};
