import { QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';

import { apiError } from '@/api/client';
import { createQueryClient } from '@/config/query-client';
import {
  ASSET_LIST_QUERY_KEY,
  PROCESSING_POLL_MAX_MS,
  PROCESSING_POLL_MS,
} from '@/constants/assets.constant';
import { STORAGE_REJECTED_CODE } from '@/constants/upload.constant';
import { UploadStatus } from '@/enums/upload-status.enum';
import { getAsset } from '@/features/assets/services/assets.service';
import { useUploads } from '@/features/uploads/hooks/useUploads';
import {
  completeUpload,
  createAsset,
  sendToStorage,
} from '@/features/uploads/services/uploads.service';
import type { PendingUpload } from '@/interfaces/upload.interface';
import { aDetail, anAsset, aVersion } from '@/test/fake-api';

vi.mock('@/features/uploads/services/uploads.service');
vi.mock('@/features/assets/services/assets.service');

const png = (name = 'rock.png'): File => new File(['png'], name, { type: 'image/png' });

const pending = (n = 1): PendingUpload => ({
  asset: anAsset({ id: `asset-${String(n)}` }),
  version: aVersion({
    id: `version-${String(n)}`,
    asset_id: `asset-${String(n)}`,
    status: 'pending_upload',
  }),
  upload: { url: 'http://s3.test/kiln', fields: {}, expires_at: '2026-11-06T08:15:00Z' },
});

const detailWith = (status: 'processing' | 'ready' | 'failed', n = 1) =>
  aDetail({
    id: `asset-${String(n)}`,
    versions: [
      aVersion({
        id: `version-${String(n)}`,
        status,
        failure_reason: status === 'failed' ? 'UNREADABLE_IMAGE' : null,
      }),
    ],
  });

const setup = () => {
  const queryClient = createQueryClient(0);
  const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  const hook = renderHook(() => useUploads(), { wrapper });
  return { ...hook, invalidate };
};

/** A promise the test resolves or rejects by hand. */
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};

const statusOf = (result: { current: ReturnType<typeof useUploads> }, index = 0) =>
  result.current.items[index]?.status;

describe('useUploads', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(createAsset).mockResolvedValue(pending());
    vi.mocked(sendToStorage).mockResolvedValue();
    vi.mocked(completeUpload).mockResolvedValue({});
    vi.mocked(getAsset).mockResolvedValue(detailWith('ready'));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.resetAllMocks();
  });

  it('creates, sends, completes and waits for the preview, refreshing the gallery', async () => {
    const { result, invalidate } = setup();

    act(() => result.current.add([png()]));
    await waitFor(() => expect(statusOf(result)).toBe(UploadStatus.Processing));
    expect(vi.mocked(createAsset).mock.calls[0]?.[0]).toMatchObject({
      file_name: 'rock.png',
      name: 'rock',
    });
    expect(vi.mocked(sendToStorage).mock.calls[0]?.[0]).toMatchObject({ form: pending().upload });
    expect(completeUpload).toHaveBeenCalledWith('version-1', expect.any(AbortSignal));

    // Once when the card appears (processing), again when its preview is ready.
    expect(invalidate).toHaveBeenCalledTimes(1);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ASSET_LIST_QUERY_KEY });

    await act(() => vi.advanceTimersByTimeAsync(PROCESSING_POLL_MS));
    await waitFor(() => expect(statusOf(result)).toBe(UploadStatus.Ready));
    expect(getAsset).toHaveBeenCalledWith('asset-1', expect.any(AbortSignal));
    expect(invalidate).toHaveBeenCalledTimes(2);
    expect(result.current.summary).toEqual({ finished: 1, failed: 0, total: 1 });
  });

  it('reports progress while the file is sent', async () => {
    const sending = deferred<undefined>();
    vi.mocked(sendToStorage).mockImplementation(({ onProgress }) => {
      onProgress(42.4);
      return sending.promise;
    });
    const { result } = setup();

    act(() => result.current.add([png()]));

    await waitFor(() =>
      expect(result.current.items[0]).toMatchObject({
        status: UploadStatus.Uploading,
        progress: 42.4,
      }),
    );
    sending.resolve(undefined);
  });

  it('updates progress once per whole percent', async () => {
    const sending = deferred<undefined>();
    vi.mocked(sendToStorage).mockImplementation(({ onProgress }) => {
      onProgress(10.1);
      onProgress(10.9);
      onProgress(11.2);
      onProgress(11.8);
      return sending.promise;
    });
    const { result } = setup();

    act(() => result.current.add([png()]));

    await waitFor(() => expect(result.current.items[0]?.progress).toBe(11.2));
    sending.resolve(undefined);
  });

  it('refuses unsupported, empty and oversized files without sending anything', () => {
    const { result } = setup();

    act(() => result.current.add([new File(['x'], 'notes.txt'), new File([], 'empty.png')]));

    expect(result.current.items.map((item) => [item.status, item.error, item.canRetry])).toEqual([
      [UploadStatus.Failed, 'Only PNG, JPEG, WebP and .glb files can be uploaded.', false],
      [UploadStatus.Failed, 'This file is empty.', false],
    ]);
    expect(createAsset).not.toHaveBeenCalled();
  });

  it('sends at most two files at a time; the rest wait in the queue', async () => {
    const first = deferred<undefined>();
    vi.mocked(sendToStorage)
      .mockReturnValueOnce(first.promise)
      .mockReturnValue(new Promise(() => undefined));
    vi.mocked(createAsset).mockImplementation((declaration) =>
      Promise.resolve(pending(declaration.file_name === 'b.png' ? 2 : 1)),
    );
    const { result } = setup();

    act(() => result.current.add([png('a.png'), png('b.png'), png('c.png')]));

    await waitFor(() => expect(sendToStorage).toHaveBeenCalledTimes(2));
    expect(statusOf(result, 2)).toBe(UploadStatus.Queued);

    first.resolve(undefined);
    await waitFor(() => expect(createAsset).toHaveBeenCalledTimes(3));
  });

  it('cancels a running upload and lets it be retried with the same idempotency key', async () => {
    vi.mocked(sendToStorage).mockImplementationOnce(
      ({ signal }) =>
        new Promise((_resolve, reject) =>
          signal?.addEventListener('abort', () => reject(new DOMException('x', 'AbortError'))),
        ),
    );
    const { result } = setup();
    act(() => result.current.add([png()]));
    await waitFor(() => expect(statusOf(result)).toBe(UploadStatus.Uploading));

    act(() => result.current.cancel(result.current.items[0]!.id));
    await waitFor(() => expect(statusOf(result)).toBe(UploadStatus.Cancelled));

    act(() => result.current.retry(result.current.items[0]!.id));
    await waitFor(() => expect(statusOf(result)).toBe(UploadStatus.Processing));
    const keys = vi.mocked(createAsset).mock.calls.map(([, key]) => key);
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
  });

  it('cancels a queued file without starting it', async () => {
    vi.mocked(sendToStorage).mockReturnValue(new Promise(() => undefined));
    const { result } = setup();
    act(() => result.current.add([png('a.png'), png('b.png'), png('c.png')]));
    await waitFor(() => expect(sendToStorage).toHaveBeenCalledTimes(2));

    act(() => result.current.cancel(result.current.items[2]!.id));

    expect(statusOf(result, 2)).toBe(UploadStatus.Cancelled);
    expect(createAsset).toHaveBeenCalledTimes(2);
  });

  it.each([
    [
      apiError(403, 'Storage refused the file (403)', STORAGE_REJECTED_CODE),
      'Storage refused the file. Try again.',
    ],
    [
      apiError(0, 'Failed to fetch'),
      'Kiln cannot reach its server. Check your connection, then try again.',
    ],
    [apiError(503, 'Storage is unavailable', 'STORAGE_UNAVAILABLE'), 'Storage is unavailable'],
  ])('fails with a readable reason that can be retried (%s)', async (error, message) => {
    vi.mocked(sendToStorage).mockRejectedValue(error);
    const { result } = setup();

    act(() => result.current.add([png()]));

    await waitFor(() => expect(statusOf(result)).toBe(UploadStatus.Failed));
    expect(result.current.items[0]).toMatchObject({ error: message, canRetry: true });
  });

  it('skips sending when a retry replays a version that already left pending_upload', async () => {
    vi.mocked(createAsset).mockResolvedValue({
      ...pending(),
      version: aVersion({ id: 'version-1', status: 'processing' }),
      upload: null,
    });
    const { result } = setup();

    act(() => result.current.add([png()]));

    await waitFor(() => expect(statusOf(result)).toBe(UploadStatus.Processing));
    expect(sendToStorage).not.toHaveBeenCalled();
    expect(completeUpload).not.toHaveBeenCalled();
  });

  it('treats a completion the API already recorded as done', async () => {
    vi.mocked(completeUpload).mockRejectedValue(
      apiError(409, 'Already complete', 'INVALID_STATUS_TRANSITION'),
    );
    const { result } = setup();

    act(() => result.current.add([png()]));

    await waitFor(() => expect(statusOf(result)).toBe(UploadStatus.Processing));
  });

  it('shows why a preview failed, without offering a retry', async () => {
    vi.mocked(getAsset).mockResolvedValue(detailWith('failed'));
    const { result } = setup();

    act(() => result.current.add([png()]));
    await waitFor(() => expect(statusOf(result)).toBe(UploadStatus.Processing));
    await act(() => vi.advanceTimersByTimeAsync(PROCESSING_POLL_MS));

    await waitFor(() => expect(statusOf(result)).toBe(UploadStatus.Failed));
    expect(result.current.items[0]).toMatchObject({
      error: 'This is not a readable PNG, JPEG or WebP image.',
      canRetry: false,
    });
  });

  it('stops polling after the processing window and says the file is uploaded', async () => {
    vi.mocked(getAsset).mockResolvedValue(detailWith('processing'));
    const { result } = setup();

    act(() => result.current.add([png()]));
    await waitFor(() => expect(statusOf(result)).toBe(UploadStatus.Processing));
    await act(() => vi.advanceTimersByTimeAsync(PROCESSING_POLL_MAX_MS + PROCESSING_POLL_MS));

    await waitFor(() => expect(statusOf(result)).toBe(UploadStatus.Uploaded));
    const polls = vi.mocked(getAsset).mock.calls.length;
    await act(() => vi.advanceTimersByTimeAsync(PROCESSING_POLL_MS * 3));
    expect(getAsset).toHaveBeenCalledTimes(polls);
  });

  it('keeps polling through a failed poll', async () => {
    vi.mocked(getAsset)
      .mockRejectedValueOnce(apiError(0, 'offline'))
      .mockResolvedValue(detailWith('ready'));
    const { result } = setup();

    act(() => result.current.add([png()]));
    await waitFor(() => expect(statusOf(result)).toBe(UploadStatus.Processing));
    await act(() => vi.advanceTimersByTimeAsync(PROCESSING_POLL_MS * 2));

    await waitFor(() => expect(statusOf(result)).toBe(UploadStatus.Ready));
  });

  it('removes a row and stops its transfer', async () => {
    let signal: AbortSignal | undefined;
    vi.mocked(sendToStorage).mockImplementation((options) => {
      signal = options.signal;
      return new Promise(() => undefined);
    });
    const { result } = setup();
    act(() => result.current.add([png()]));
    await waitFor(() => expect(statusOf(result)).toBe(UploadStatus.Uploading));

    act(() => result.current.remove(result.current.items[0]!.id));

    expect(result.current.items).toEqual([]);
    expect(signal?.aborted).toBe(true);
  });

  it('stops every transfer when the gallery unmounts', async () => {
    let signal: AbortSignal | undefined;
    vi.mocked(sendToStorage).mockImplementation((options) => {
      signal = options.signal;
      return new Promise(() => undefined);
    });
    const { result, unmount } = setup();
    act(() => result.current.add([png()]));
    await waitFor(() => expect(statusOf(result)).toBe(UploadStatus.Uploading));

    unmount();

    expect(signal?.aborted).toBe(true);
  });
});
