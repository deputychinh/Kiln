import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { type ComponentType, type ReactElement, useEffect } from 'react';
import type { Mock } from 'vitest';

import { ViewerError } from '@/enums/viewer-error.enum';
import { ModelViewer } from '@/features/viewer/components/ModelViewer';
import type { ModelSceneProps, ViewerController } from '@/interfaces/viewer.interface';
import { urlOf } from '@/test/fake-api';
import { buildGlb, cubeJson, cubeGlb } from '@/test/glb';
import { setReducedMotion } from '@/test/viewport';

const FILE = 'http://s3.test/kiln/assets/a/v2/m.glb';
const signed = (signature: string) => `${FILE}?X-Amz-Signature=${signature}`;
const PREVIEW = 'http://s3.test/kiln/thumbs/a/m.webp?sig=1';
const CUBE = cubeGlb();

const fileReply = (bytes: ArrayBuffer = CUBE, status = 200): Response =>
  new Response(bytes, {
    status,
    headers: { 'Content-Length': String(bytes.byteLength) },
  });

const controller = (): ViewerController => ({
  rotate: vi.fn(),
  pan: vi.fn(),
  zoom: vi.fn(),
  reset: vi.fn(),
});

/** A renderer that is ready at once, or fails with `failWith`; it records what it was given. */
const fakeScene = (view: ViewerController, failWith?: ViewerError) => {
  const seen: ModelSceneProps[] = [];
  const Scene = (props: ModelSceneProps): ReactElement => {
    seen.push(props);
    const { onReady, onError } = props;
    useEffect(() => {
      if (failWith) onError(failWith);
      else onReady(view);
    }, [onReady, onError]);
    return <canvas data-testid="scene" />;
  };
  return { Scene, seen };
};

interface RenderViewerProps {
  url?: string;
  sizeBytes?: number;
  previewUrl?: string | null;
  scene?: ComponentType<ModelSceneProps>;
  onRetry?: Mock<() => Promise<void>>;
}

const renderViewer = ({
  url = signed('1'),
  sizeBytes = CUBE.byteLength,
  previewUrl = PREVIEW,
  scene = fakeScene(controller()).Scene,
  onRetry = vi.fn(() => Promise.resolve()),
}: RenderViewerProps = {}) => {
  const loadScene = () => Promise.resolve({ default: scene });
  const props = {
    versionNumber: 2,
    sizeBytes,
    previewUrl,
    onPreviewError: vi.fn(),
    onRetry,
    loadScene,
  };
  const view = render(<ModelViewer fileUrl={url} {...props} />);
  return {
    ...view,
    onRetry,
    rerenderWith: (next: string) => view.rerender(<ModelViewer fileUrl={next} {...props} />),
  };
};

const stage = () => screen.getByRole('application', { name: '3D view of version 2' });
const resetButton = () => screen.getByRole('button', { name: 'Reset view' });

describe('ModelViewer', () => {
  afterEach(() => vi.restoreAllMocks());

  it('shows download progress over the still preview, then the model with its controls', async () => {
    let finish: (response: Response) => void = () => undefined;
    vi.spyOn(globalThis, 'fetch').mockReturnValue(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    renderViewer();

    expect(
      within(stage()).getByRole('img', { name: 'Still preview of version 2' }),
    ).toHaveAttribute('src', PREVIEW);
    expect(await screen.findByRole('progressbar', { name: 'Downloading version 2' })).toBeVisible();
    expect(resetButton()).toBeDisabled();
    expect(stage()).not.toHaveAttribute('tabindex', '0');

    act(() => finish(fileReply()));

    await waitFor(() => expect(resetButton()).toBeEnabled());
    expect(within(stage()).getByTestId('scene')).toBeVisible();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    expect(within(stage()).queryByRole('img')).not.toBeInTheDocument();
    expect(stage()).toHaveAttribute('tabindex', '0');
    expect(stage()).toHaveAccessibleDescription(/arrow keys rotate/);
  });

  it('says it is preparing the model between the download and the first frame', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(fileReply());
    const Pending = (): ReactElement => <canvas />;
    renderViewer({ scene: Pending });

    expect(await screen.findByText('Preparing the model…')).toBeVisible();
    expect(resetButton()).toBeDisabled();
  });

  it('turns, moves, zooms and resets the view with the buttons', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(fileReply());
    const view = controller();
    renderViewer({ scene: fakeScene(view).Scene });
    await waitFor(() => expect(resetButton()).toBeEnabled());
    const user = userEvent.setup();

    for (const name of ['Rotate left', 'Rotate right', 'Rotate up', 'Rotate down']) {
      await user.click(screen.getByRole('button', { name }));
    }
    for (const name of ['Move left', 'Move right', 'Move up', 'Move down']) {
      await user.click(screen.getByRole('button', { name }));
    }
    await user.click(screen.getByRole('button', { name: 'Zoom in' }));
    await user.click(screen.getByRole('button', { name: 'Zoom out' }));
    await user.click(resetButton());

    expect(vi.mocked(view.rotate).mock.calls).toEqual([
      [1, 0],
      [-1, 0],
      [0, 1],
      [0, -1],
    ]);
    expect(vi.mocked(view.pan).mock.calls).toEqual([
      [-1, 0],
      [1, 0],
      [0, 1],
      [0, -1],
    ]);
    expect(vi.mocked(view.zoom).mock.calls).toEqual([[1], [-1]]);
    expect(view.reset).toHaveBeenCalledTimes(1);
  });

  it('turns with the arrow keys, moves with Shift, zooms with + and − and resets with 0', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(fileReply());
    const view = controller();
    renderViewer({ scene: fakeScene(view).Scene });
    await waitFor(() => expect(resetButton()).toBeEnabled());
    const user = userEvent.setup();

    stage().focus();
    await user.keyboard('{ArrowLeft}{ArrowRight}{ArrowUp}{ArrowDown}');
    await user.keyboard('{Shift>}{ArrowLeft}{ArrowRight}{ArrowUp}{ArrowDown}{/Shift}');
    await user.keyboard('+=-_0{Home}x');

    expect(vi.mocked(view.rotate).mock.calls).toEqual([
      [1, 0],
      [-1, 0],
      [0, 1],
      [0, -1],
    ]);
    expect(vi.mocked(view.pan).mock.calls).toEqual([
      [-1, 0],
      [1, 0],
      [0, 1],
      [0, -1],
    ]);
    expect(vi.mocked(view.zoom).mock.calls).toEqual([[1], [1], [-1], [-1]]);
    expect(view.reset).toHaveBeenCalledTimes(2);
  });

  it('keeps the page from scrolling on the keys it uses, and leaves other keys alone', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(fileReply());
    renderViewer();
    await waitFor(() => expect(resetButton()).toBeEnabled());

    const arrow = new KeyboardEvent('keydown', {
      key: 'ArrowDown',
      bubbles: true,
      cancelable: true,
    });
    const tab = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
    const withCtrl = new KeyboardEvent('keydown', {
      key: '+',
      ctrlKey: true,
      bubbles: true,
      cancelable: true,
    });
    stage().dispatchEvent(arrow);
    stage().dispatchEvent(tab);
    stage().dispatchEvent(withCtrl);

    expect(arrow.defaultPrevented).toBe(true);
    expect(tab.defaultPrevented).toBe(false);
    expect(withCtrl.defaultPrevented).toBe(false); // the browser's own zoom
  });

  it('ignores the keys until the model is ready', () => {
    vi.spyOn(globalThis, 'fetch').mockReturnValue(new Promise(() => undefined));
    const view = controller();
    renderViewer({ scene: fakeScene(view).Scene });

    const arrow = new KeyboardEvent('keydown', {
      key: 'ArrowLeft',
      bubbles: true,
      cancelable: true,
    });
    stage().dispatchEvent(arrow);

    expect(view.rotate).not.toHaveBeenCalled();
    expect(arrow.defaultPrevented).toBe(false);
  });

  it('falls back to the still preview when the download fails, and retries with a fresh link', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(null, { status: 403 }))
      .mockResolvedValue(fileReply());
    const { onRetry, rerenderWith } = renderViewer();

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(
      'Could not download the model. Check your connection, then try again.',
    );
    expect(alert).toHaveTextContent('Showing the still preview instead.');
    expect(within(stage()).getByRole('img', { name: 'Still preview of version 2' })).toBeVisible();
    expect(resetButton()).toBeDisabled();

    onRetry.mockImplementation(() => {
      rerenderWith(signed('2'));
      return Promise.resolve();
    });
    await userEvent.click(within(alert).getByRole('button', { name: 'Try again' }));

    await waitFor(() => expect(resetButton()).toBeEnabled());
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls.map(([input]) => urlOf(input))).toEqual([signed('1'), signed('2')]);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('refuses a model over 256 MB without downloading it, and offers no retry', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch');
    renderViewer({ sizeBytes: 256 * 1024 * 1024 + 1 });

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This model is larger than the 256 MB the viewer opens.',
    );
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([
    [
      'points outside itself',
      buildGlb({ ...cubeJson, images: [{ uri: 'https://evil.test/a.png' }] }),
      'This model points to files outside it, which Kiln never downloads.',
    ],
    [
      'needs a decoder',
      buildGlb({ ...cubeJson, extensionsRequired: ['KHR_draco_mesh_compression'] }),
      'This model uses compression the viewer does not support yet (Draco, meshopt or Basis).',
    ],
    [
      'is not a .glb',
      new TextEncoder().encode('not a model at all, sorry').buffer,
      'This file is not a glTF binary (.glb) the viewer can read.',
    ],
  ])('never hands a file that %s to the renderer', async (_case, bytes, message) => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(fileReply(bytes));
    const { Scene, seen } = fakeScene(controller());
    renderViewer({ scene: Scene, sizeBytes: bytes.byteLength });

    expect(await screen.findByRole('alert')).toHaveTextContent(message);
    expect(seen).toEqual([]);
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
  });

  it('falls back to the still preview when the renderer cannot start', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(fileReply());
    renderViewer({ scene: fakeScene(controller(), ViewerError.WebGl).Scene });

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This browser could not start 3D graphics (WebGL).',
    );
    expect(within(stage()).getByRole('img', { name: 'Still preview of version 2' })).toBeVisible();
    expect(within(stage()).queryByTestId('scene')).toBeNull();
  });

  it('maps a scene that fails while drawing to an unreadable model, not a failed download', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined); // React reports the throw
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(fileReply());
    const Broken = (): ReactElement => {
      throw new Error('THREE.WebGLRenderer: shader error');
    };
    renderViewer({ scene: Broken });

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This file is not a glTF binary (.glb) the viewer can read.',
    );
    expect(within(stage()).getByRole('img', { name: 'Still preview of version 2' })).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
  });

  it('offers a retry when the viewer code cannot be loaded, and loads it again', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => Promise.resolve(fileReply()));
    const { Scene } = fakeScene(controller());
    const loadScene = vi
      .fn<() => Promise<{ default: ComponentType<ModelSceneProps> }>>()
      .mockRejectedValueOnce(new TypeError('Failed to fetch dynamically imported module'))
      .mockResolvedValue({ default: Scene });
    render(
      <ModelViewer
        fileUrl={signed('1')}
        sizeBytes={CUBE.byteLength}
        versionNumber={2}
        previewUrl={PREVIEW}
        onPreviewError={vi.fn()}
        onRetry={() => Promise.resolve()}
        loadScene={loadScene}
      />,
    );

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(
      'Could not load the 3D viewer. Check your connection, then try again.',
    );
    expect(within(stage()).getByRole('img', { name: 'Still preview of version 2' })).toBeVisible();
    await userEvent.click(within(alert).getByRole('button', { name: 'Try again' }));

    await waitFor(() => expect(resetButton()).toBeEnabled());
    expect(loadScene).toHaveBeenCalledTimes(2);
  });

  it('keeps the first error when the scene reports another', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(fileReply());
    const Twice = ({ onError }: ModelSceneProps): ReactElement => {
      useEffect(() => {
        onError(ViewerError.WebGl);
        onError(ViewerError.Unreadable);
      }, [onError]);
      return <canvas />;
    };
    renderViewer({ scene: Twice });

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This browser could not start 3D graphics (WebGL).',
    );
  });

  it('says so when there is no still preview to fall back to', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 500 }));
    renderViewer({ previewUrl: null });

    await screen.findByRole('alert');
    expect(within(stage()).getByText('No still preview')).toBeVisible();
  });

  it('keeps the loaded model when the same file comes back with a new signature', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(fileReply());
    const { rerenderWith } = renderViewer();
    await waitFor(() => expect(resetButton()).toBeEnabled());

    rerenderWith(signed('2'));

    expect(resetButton()).toBeEnabled();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('downloads again when the link points at another file', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(fileReply());
    const { rerenderWith } = renderViewer();
    await waitFor(() => expect(resetButton()).toBeEnabled());

    rerenderWith('http://s3.test/kiln/assets/a/v3/other.glb?X-Amz-Signature=1');

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });

  it('stops the download when it is left', () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockReturnValue(new Promise(() => undefined));
    const { unmount } = renderViewer();

    unmount();

    const init = fetchMock.mock.calls[0]?.[1];
    expect(init?.signal?.aborted).toBe(true);
  });

  it('tells the renderer when the person asked for reduced motion', async () => {
    setReducedMotion(true);
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(fileReply());
    const { Scene, seen } = fakeScene(controller());
    renderViewer({ scene: Scene });

    await waitFor(() => expect(resetButton()).toBeEnabled());
    expect(seen.at(-1)?.isReducedMotion).toBe(true);
  });
});
