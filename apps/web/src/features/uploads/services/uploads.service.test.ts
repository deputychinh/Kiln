import { isApiError } from '@/api/client';
import { UPLOAD_API_TIMEOUT_MS, UPLOAD_STALLED_CODE } from '@/constants/upload.constant';
import {
  completeUpload,
  createAsset,
  sendToStorage,
} from '@/features/uploads/services/uploads.service';
import type { SignedUploadForm } from '@/interfaces/upload.interface';
import { fakeApi, json, urlOf } from '@/test/fake-api';

const FORM: SignedUploadForm = {
  url: 'http://s3.test/kiln',
  fields: { key: 'uploads/a/v', policy: 'p', 'x-amz-signature': 's' },
  expires_at: '2026-11-06T08:15:00Z',
};

type Listener = (event: { lengthComputable: boolean; loaded: number; total: number }) => void;

/** A stand-in for XMLHttpRequest that the test drives by hand. */
const fakeRequest = () => {
  const listeners = new Map<string, Listener>();
  const uploadListeners = new Map<string, Listener>();
  const request = {
    status: 0,
    sent: null as FormData | null,
    opened: [] as string[],
    upload: {
      addEventListener: (type: string, listener: Listener) => uploadListeners.set(type, listener),
    },
    addEventListener: (type: string, listener: Listener) => listeners.set(type, listener),
    open: (method: string, url: string) => request.opened.push(method, url),
    send: (body: FormData) => {
      request.sent = body;
    },
    abort: vi.fn(() => listeners.get('abort')?.({ lengthComputable: false, loaded: 0, total: 0 })),
    fire: (type: string, status = 0) => {
      request.status = status;
      listeners.get(type)?.({ lengthComputable: false, loaded: 0, total: 0 });
    },
    progress: (loaded: number, total: number) =>
      uploadListeners.get('progress')?.({ lengthComputable: true, loaded, total }),
  };
  return request;
};

const file = new File(['png'], 'rock.png', { type: 'image/png' });

describe('createAsset', () => {
  afterEach(() => vi.restoreAllMocks());

  it('posts the declaration with the idempotency key', async () => {
    const fetchMock = fakeApi({ '/api/v1/assets': [json({ ok: 1 }, 201)] });
    const declaration = {
      file_name: 'rock.png',
      content_type: 'image/png',
      size_bytes: 3,
      name: 'rock',
    };

    await createAsset(declaration, 'key-1');

    const [input, init] = fetchMock.mock.calls[0] ?? [];
    expect(urlOf(input)).toBe('http://api.test/api/v1/assets');
    expect(init?.headers).toMatchObject({ 'Idempotency-Key': 'key-1' });
    expect(JSON.parse(init?.body as string)).toEqual(declaration);
  });
});

describe('timeouts', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  /** fetch that never answers but rejects like the browser when its signal aborts. */
  const hangingFetch = () =>
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      (_input, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () =>
            reject(new DOMException('The operation was aborted', 'AbortError')),
          );
        }),
    );

  it('fails a create that takes longer than 30 s as stalled', async () => {
    hangingFetch();
    const declaration = { file_name: 'a.png', content_type: 'image/png', size_bytes: 1, name: 'a' };
    const created = createAsset(declaration, 'key').catch((caught: unknown) => caught);

    await vi.advanceTimersByTimeAsync(UPLOAD_API_TIMEOUT_MS);

    expect(await created).toMatchObject({ status: 0, code: UPLOAD_STALLED_CODE });
  });

  it('fails a completion that takes longer than 30 s as stalled', async () => {
    hangingFetch();
    const completed = completeUpload('v1').catch((caught: unknown) => caught);

    await vi.advanceTimersByTimeAsync(UPLOAD_API_TIMEOUT_MS);

    expect(await completed).toMatchObject({ code: UPLOAD_STALLED_CODE });
  });

  it('still reports a cancel as an abort, not as a timeout', async () => {
    hangingFetch();
    const controller = new AbortController();
    const completed = completeUpload('v1', controller.signal).catch((caught: unknown) => caught);

    controller.abort();

    expect(await completed).toMatchObject({ name: 'AbortError' });
  });

  it('fails a transfer with no progress for 60 s as stalled, and keeps one that moves', async () => {
    const moving = fakeRequest();
    const stalled = fakeRequest();
    const kept = sendToStorage({
      form: FORM,
      file,
      onProgress: vi.fn(),
      createRequest: () => moving,
    });
    const lost = sendToStorage({
      form: FORM,
      file,
      onProgress: vi.fn(),
      createRequest: () => stalled,
    }).catch((caught: unknown) => caught);

    for (let second = 0; second < 90; second += 30) {
      moving.progress(second + 1, 100);
      await vi.advanceTimersByTimeAsync(30_000);
    }
    moving.fire('load', 204);

    await expect(kept).resolves.toBeUndefined();
    expect(await lost).toMatchObject({ status: 0, code: UPLOAD_STALLED_CODE });
    expect(stalled.abort).toHaveBeenCalledTimes(1);
  });
});

describe('completeUpload', () => {
  afterEach(() => vi.restoreAllMocks());

  it('posts to the version completions path', async () => {
    const fetchMock = fakeApi({ '/api/v1/asset-versions/': [json({}, 200)] });

    await completeUpload('v/1');

    expect(urlOf(fetchMock.mock.calls[0]?.[0])).toBe(
      'http://api.test/api/v1/asset-versions/v%2F1/completions',
    );
  });
});

describe('sendToStorage', () => {
  it('posts every signed field, then the file, to the form URL and reports progress', async () => {
    const request = fakeRequest();
    const onProgress = vi.fn();
    const sent = sendToStorage({ form: FORM, file, onProgress, createRequest: () => request });

    request.progress(25, 100);
    request.progress(100, 100);
    request.fire('load', 204);
    await sent;

    expect(request.opened).toEqual(['POST', 'http://s3.test/kiln']);
    expect([...(request.sent?.keys() ?? [])]).toEqual(['key', 'policy', 'x-amz-signature', 'file']);
    expect(request.sent?.get('file')).toBe(file);
    expect(onProgress.mock.calls).toEqual([[25], [100]]);
  });

  it('rejects with the storage status when storage refuses the file', async () => {
    const request = fakeRequest();
    const sent = sendToStorage({
      form: FORM,
      file,
      onProgress: vi.fn(),
      createRequest: () => request,
    });

    request.fire('load', 403);
    const error: unknown = await sent.catch((caught: unknown) => caught);

    expect(isApiError(error)).toBe(true);
    expect(error).toMatchObject({ status: 403, code: 'STORAGE_REJECTED' });
  });

  it('rejects as unreachable on a network error', async () => {
    const request = fakeRequest();
    const sent = sendToStorage({
      form: FORM,
      file,
      onProgress: vi.fn(),
      createRequest: () => request,
    });

    request.fire('error');

    await expect(sent).rejects.toMatchObject({ status: 0 });
  });

  it('aborts the transfer when the signal fires, and rejects with an AbortError', async () => {
    const request = fakeRequest();
    const controller = new AbortController();
    const sent = sendToStorage({
      form: FORM,
      file,
      onProgress: vi.fn(),
      signal: controller.signal,
      createRequest: () => request,
    });

    controller.abort();

    await expect(sent).rejects.toMatchObject({ name: 'AbortError' });
    expect(request.abort).toHaveBeenCalledTimes(1);
  });

  it('never starts when the signal already fired', async () => {
    const request = fakeRequest();
    const controller = new AbortController();
    controller.abort();

    await expect(
      sendToStorage({
        form: FORM,
        file,
        onProgress: vi.fn(),
        signal: controller.signal,
        createRequest: () => request,
      }),
    ).rejects.toMatchObject({ name: 'AbortError' });
    expect(request.sent).toBeNull();
  });

  it('ignores progress events without a known total', async () => {
    const request = fakeRequest();
    const onProgress = vi.fn();
    const sent = sendToStorage({ form: FORM, file, onProgress, createRequest: () => request });

    request.progress(10, 0);
    request.fire('load', 201);
    await sent;

    expect(onProgress).not.toHaveBeenCalled();
  });
});
