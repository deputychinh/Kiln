import { MODEL_VIEWER_MAX_BYTES } from '@/constants/viewer.constant';
import { ViewerError } from '@/enums/viewer-error.enum';
import { downloadModel } from '@/features/viewer/services/model-file.service';
import type { DownloadProgress } from '@/interfaces/viewer.interface';
import { viewerErrorOf } from '@/utils/viewer.util';

const URL_ = 'http://s3.test/kiln/assets/a/v1/m.glb?X-Amz-Signature=1';

const streamOf = (chunks: Uint8Array[]): ReadableStream<Uint8Array> =>
  new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(chunk));
      controller.close();
    },
  });

const reply = (chunks: Uint8Array[], headers: Record<string, string> = {}, status = 200) =>
  vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValue(new Response(streamOf(chunks), { status, headers }));

const failureOf = async (promise: Promise<unknown>): Promise<ViewerError> => {
  try {
    await promise;
  } catch (error) {
    return viewerErrorOf(error);
  }
  throw new Error('expected a failure');
};

describe('downloadModel', () => {
  afterEach(() => vi.restoreAllMocks());

  it('streams the file with progress, without cookies and without following redirects', async () => {
    const fetchMock = reply([new Uint8Array([1, 2]), new Uint8Array([3, 4, 5])], {
      'Content-Length': '5',
    });
    const progress: DownloadProgress[] = [];

    const buffer = await downloadModel(URL_, {
      declaredBytes: 5,
      onProgress: (step) => progress.push(step),
    });

    expect([...new Uint8Array(buffer)]).toEqual([1, 2, 3, 4, 5]);
    expect(progress).toEqual([
      { loaded: 0, total: 5 },
      { loaded: 2, total: 5 },
      { loaded: 5, total: 5 },
    ]);
    expect(fetchMock).toHaveBeenCalledWith(
      URL_,
      expect.objectContaining({ credentials: 'omit', redirect: 'error', mode: 'cors' }),
    );
  });

  it('takes the total from the declared size when the server sends no length', async () => {
    reply([new Uint8Array([1, 2, 3])]);
    const progress: DownloadProgress[] = [];

    await downloadModel(URL_, { declaredBytes: 3, onProgress: (step) => progress.push(step) });

    expect(progress.at(-1)).toEqual({ loaded: 3, total: 3 });
  });

  it('refuses a declared size over the cap without downloading anything', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch');

    const error = await failureOf(
      downloadModel(URL_, { declaredBytes: MODEL_VIEWER_MAX_BYTES + 1 }),
    );

    expect(error).toBe(ViewerError.TooLarge);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('accepts a file of exactly the cap', async () => {
    reply([new Uint8Array(4)], { 'Content-Length': '4' });
    await expect(downloadModel(URL_, { declaredBytes: 4, maxBytes: 4 })).resolves.toBeInstanceOf(
      ArrayBuffer,
    );
  });

  it('stops when the server announces more than the cap', async () => {
    reply([new Uint8Array(4)], { 'Content-Length': '5' });
    expect(await failureOf(downloadModel(URL_, { declaredBytes: 4, maxBytes: 4 }))).toBe(
      ViewerError.TooLarge,
    );
  });

  it('stops as soon as the streamed bytes pass the cap, whatever the headers said', async () => {
    reply([new Uint8Array(3), new Uint8Array(3)], { 'Content-Length': '3' });
    expect(await failureOf(downloadModel(URL_, { declaredBytes: 3, maxBytes: 4 }))).toBe(
      ViewerError.TooLarge,
    );
  });

  it('reports an HTTP error, such as an expired link, as a failed download', async () => {
    reply([], {}, 403);
    expect(await failureOf(downloadModel(URL_, { declaredBytes: 4 }))).toBe(ViewerError.Download);
  });

  it('reports a network failure as a failed download', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));
    expect(await failureOf(downloadModel(URL_, { declaredBytes: 4 }))).toBe(ViewerError.Download);
  });

  it('rethrows a cancellation as it is, not as a failure', async () => {
    const controller = new AbortController();
    controller.abort();
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new DOMException('aborted', 'AbortError'));

    await expect(
      downloadModel(URL_, { declaredBytes: 4, signal: controller.signal }),
    ).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('reads a response without a stream in one piece', async () => {
    const response = new Response(new Uint8Array([7, 8]));
    Object.defineProperty(response, 'body', { value: null });
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(response);
    const buffer = await downloadModel(URL_, { declaredBytes: 2 });
    expect([...new Uint8Array(buffer)]).toEqual([7, 8]);
  });
});
