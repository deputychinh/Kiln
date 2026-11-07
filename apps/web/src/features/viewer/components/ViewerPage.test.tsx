import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { type ReactElement, useEffect } from 'react';

import type { ModelSceneProps } from '@/interfaces/viewer.interface';
import { aDetail, aVersion, countRequests, fakeApi, json, problem, urlOf } from '@/test/fake-api';
import { cubeGlb } from '@/test/glb';
import { renderApp } from '@/test/render-app';

// jsdom has no WebGL: the lazily loaded scene is replaced by one that is ready at once.
vi.mock('@/features/viewer/components/ModelScene', () => ({
  ModelScene: ({ onReady }: ModelSceneProps): ReactElement => {
    useEffect(() => {
      onReady({
        rotate: () => undefined,
        pan: () => undefined,
        zoom: () => undefined,
        reset: () => undefined,
      });
    }, [onReady]);
    return <canvas data-testid="scene" />;
  },
}));

const CUBE = cubeGlb();
const asset = aDetail().id;
const DETAIL = `/api/v1/assets/${asset}`;
const VIEW = `/assets/${asset}/view`;
const FILE_PATH = '/kiln/assets/crate/v';

const model = (number: number, overrides = {}) =>
  aVersion({
    id: `m${String(number)}`,
    number,
    content_type: 'model/gltf-binary',
    file_name: `crate_v${String(number)}.glb`,
    size_bytes: CUBE.byteLength,
    thumbnail_url: `http://s3.test/thumbs/m${String(number)}.webp?sig=1`,
    download_url: `http://s3.test${FILE_PATH}${String(number)}.glb?sig=1`,
    ...overrides,
  });

const crate = aDetail({
  name: 'crate',
  kind: 'model',
  versions: [model(1), model(2), model(3, { status: 'processing', download_url: null })],
});

const file = (): Response =>
  new Response(CUBE, { headers: { 'Content-Length': String(CUBE.byteLength) } });

const resetButton = () => screen.getByRole('button', { name: 'Reset view' });

describe('ViewerPage', () => {
  afterEach(() => vi.restoreAllMocks());

  it('opens a model version from its asset in 3D, focused on the heading, with its facts', async () => {
    fakeApi({ [DETAIL]: [json(crate)], [FILE_PATH]: [file()] });
    renderApp(`/assets/${asset}`);

    await userEvent.click(await screen.findByRole('link', { name: 'View version 1 in 3D' }));

    const heading = await screen.findByRole('heading', {
      level: 1,
      name: 'Version 1 of crate in 3D',
    });
    await waitFor(() => expect(heading).toHaveFocus());
    await waitFor(() => expect(resetButton()).toBeEnabled());
    const stage = screen.getByRole('application', { name: '3D view of version 1' });
    expect(within(stage).getByTestId('scene')).toBeVisible();
    expect(screen.getByText(/crate_v1\.glb/)).toBeVisible();
    expect(screen.getByRole('link', { name: 'Back to the asset' })).toHaveAttribute(
      'href',
      `/assets/${asset}`,
    );
  });

  it('shows the newest ready version when the URL names none', async () => {
    const fetchMock = fakeApi({ [DETAIL]: [json(crate)], [FILE_PATH]: [file()] });
    const { router } = renderApp(VIEW);

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Version 2 of crate in 3D' }),
    ).toBeVisible();
    await waitFor(() => expect(resetButton()).toBeEnabled());
    expect(fetchMock.mock.calls.map(([input]) => urlOf(input))).toContain(
      `http://s3.test${FILE_PATH}2.glb?sig=1`,
    );
    expect(router.state.location.search).toEqual({});
  });

  it.each([
    ['does not exist', '9'],
    ['is not ready', '3'],
    ['is not a number', 'abc'],
  ])('corrects a version that %s in place, without a new history entry', async (_case, raw) => {
    fakeApi({ [DETAIL]: [json(crate)], [FILE_PATH]: [file()] });
    const { router } = renderApp(`${VIEW}?version=${raw}`);

    await screen.findByRole('heading', { level: 1, name: 'Version 2 of crate in 3D' });
    await waitFor(() => expect(router.state.location.search).toEqual({ version: 2 }));
    expect(router.history.length).toBe(1);
  });

  it('fetches a fresh link for the file when a failed download is retried', async () => {
    const fetchMock = fakeApi({
      [DETAIL]: [json(crate)],
      [FILE_PATH]: [new Response(null, { status: 403 }), file()],
    });
    renderApp(`${VIEW}?version=1`);

    const alert = await screen.findByRole('alert');
    await userEvent.click(within(alert).getByRole('button', { name: 'Try again' }));

    await waitFor(() => expect(resetButton()).toBeEnabled());
    expect(countRequests(fetchMock, DETAIL)).toBe(2);
  });

  it('says an image has nothing to view in 3D, with a way back', async () => {
    fakeApi({ [DETAIL]: [json(aDetail())] });
    renderApp(`${VIEW}?version=1`);

    expect(await screen.findByRole('heading', { name: 'Nothing to view in 3D' })).toBeVisible();
    expect(
      screen.getByText('Only models open in the 3D viewer, and this asset is an image.'),
    ).toBeVisible();
    expect(screen.getByRole('link', { name: 'Back to the asset' })).toBeVisible();
  });

  it('says when no version of a model is ready yet', async () => {
    fakeApi({
      [DETAIL]: [
        json(
          aDetail({
            kind: 'model',
            versions: [model(1, { status: 'processing', download_url: null })],
          }),
        ),
      ],
    });
    renderApp(VIEW);

    expect(
      await screen.findByText(
        'No version of this model is ready yet. A version opens here once it is processed.',
      ),
    ).toBeVisible();
  });

  it('says the asset was not found', async () => {
    fakeApi({ [DETAIL]: [problem(404, 'Not Found', 'ASSET_NOT_FOUND')] });
    renderApp(VIEW);

    expect(await screen.findByRole('heading', { level: 1, name: 'Asset not found' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'All assets' })).toBeVisible();
  });

  it('offers a retry when the asset cannot be loaded', async () => {
    const failed = problem(500, 'Server error', 'INTERNAL');
    // The query retries server errors on its own first (QUERY_MAX_RETRIES).
    fakeApi({
      [DETAIL]: [failed, failed, failed, json(crate)],
      [FILE_PATH]: [file()],
    });
    renderApp(VIEW);

    await screen.findByRole('heading', { level: 1, name: 'Could not load this asset' });
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Version 2 of crate in 3D' }),
    ).toBeVisible();
  });

  it('shows a loading state while the asset loads', async () => {
    fakeApi({ [DETAIL]: [json(crate)], [FILE_PATH]: [file()] });
    renderApp(VIEW);

    expect(await screen.findByText('Loading the asset…')).toBeInTheDocument();
  });
});
