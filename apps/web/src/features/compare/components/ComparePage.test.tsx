import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { aDetail, aVersion, fakeApi, json, problem } from '@/test/fake-api';
import { renderApp } from '@/test/render-app';

const asset = aDetail().id;
const DETAIL = `/api/v1/assets/${asset}`;
const COMPARE = `/assets/${asset}/compare`;

const v = (number: number, overrides = {}) =>
  aVersion({
    id: `v${String(number)}`,
    number,
    file_name: `rock_albedo_v${String(number)}.png`,
    thumbnail_url: `http://s3.test/thumbs/v${String(number)}.webp?sig=1`,
    ...overrides,
  });

const threeVersions = aDetail({
  versions: [v(1, { size_bytes: 1_000_000 }), v(2, { size_bytes: 1_200_000 }), v(3)],
});

const pane = (name: string) => screen.getByRole('figure', { name });

describe('ComparePage', () => {
  afterEach(() => vi.restoreAllMocks());

  it('shows the newest version against the one before it, with facts and the size change', async () => {
    fakeApi({ [DETAIL]: [json(threeVersions)] });
    renderApp(COMPARE);

    const heading = await screen.findByRole('heading', {
      level: 1,
      name: 'Compare versions of rock_albedo',
    });
    await waitFor(() => expect(heading).toHaveFocus());
    expect(within(pane('Version 2')).getByRole('img')).toHaveAttribute(
      'src',
      'http://s3.test/thumbs/v2.webp?sig=1',
    );
    expect(pane('Version 2')).toHaveTextContent('rock_albedo_v2.png');
    expect(pane('Version 2')).toHaveTextContent('Ready');
    expect(pane('Version 3')).toHaveTextContent('1.5 MB');
    expect(screen.getByText('Version 3 is 300 kB larger than version 2.')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Back to the asset' })).toHaveAttribute(
      'href',
      `/assets/${asset}`,
    );
  });

  it('records the chosen pair in the URL and shows it', async () => {
    fakeApi({ [DETAIL]: [json(threeVersions)] });
    const { router } = renderApp(COMPARE);

    await userEvent.selectOptions(
      await screen.findByRole('combobox', { name: 'Left version' }),
      '1',
    );

    await waitFor(() => expect(router.state.location.search).toMatchObject({ left: 1 }));
    expect(pane('Version 1')).toHaveTextContent('rock_albedo_v1.png');
    expect(screen.getByText('Version 3 is 500 kB larger than version 1.')).toBeVisible();
  });

  it('swaps the sides when a picker chooses the version the other side shows', async () => {
    fakeApi({ [DETAIL]: [json(threeVersions)] });
    const { router } = renderApp(`${COMPARE}?left=2&right=3`);

    await userEvent.selectOptions(
      await screen.findByRole('combobox', { name: 'Left version' }),
      '3',
    );

    await waitFor(() => expect(router.state.location.search).toMatchObject({ left: 3, right: 2 }));
  });

  it('lays the right version over the left in Swipe and reveals it with a labelled slider', async () => {
    fakeApi({ [DETAIL]: [json(threeVersions)] });
    const { router } = renderApp(`${COMPARE}?mode=swipe`);

    const slider = await screen.findByRole('slider', {
      name: 'Reveal version 3 over version 2',
    });
    expect(slider).toHaveValue('50');
    fireEvent.change(slider, { target: { value: '80' } });

    const stage = screen.getByRole('group', { name: 'Version 3 over version 2' });
    expect(stage.style.getPropertyValue('--compare-reveal')).toBe('80%');
    expect(within(stage).getAllByRole('img')).toHaveLength(2);
    await userEvent.click(screen.getByRole('radio', { name: 'Side by side' }));
    await waitFor(() => expect(router.state.location.search).toMatchObject({ mode: 'side' }));
  });

  it('explains a missing preview and offers no Swipe without both previews', async () => {
    fakeApi({
      [DETAIL]: [
        json(
          aDetail({
            versions: [
              v(1),
              v(2, { status: 'failed', failure_reason: 'IMAGE_TOO_LARGE', thumbnail_url: null }),
            ],
          }),
        ),
      ],
    });
    renderApp(`${COMPARE}?mode=swipe`);

    const failed = await screen.findByRole('figure', { name: 'Version 2' });
    expect(failed).toHaveTextContent('Failed');
    expect(failed).toHaveTextContent('The image has too many pixels to preview.');
    expect(within(failed).queryByRole('img')).not.toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Swipe' })).toBeDisabled();
    expect(screen.getByText('Swipe needs a preview of both versions.')).toBeVisible();
    expect(screen.queryByRole('slider')).not.toBeInTheDocument();
  });

  it('says there is nothing to compare with one version, with a way back', async () => {
    fakeApi({ [DETAIL]: [json(aDetail({ versions: [v(1)] }))] });
    renderApp(COMPARE);

    expect(await screen.findByText('Nothing to compare yet')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Back to the asset' })).toBeVisible();
  });

  it('corrects a URL that names versions that do not exist, without a new history entry', async () => {
    fakeApi({ [DETAIL]: [json(threeVersions)] });
    const { router } = renderApp(`${COMPARE}?left=8&right=9`);

    await waitFor(() => expect(router.state.location.search).toEqual({ left: 2, right: 3 }));
    expect(router.history.length).toBe(1);
    expect(pane('Version 2')).toBeVisible();
  });

  it('says the asset was not found', async () => {
    fakeApi({ [DETAIL]: [problem(404, 'Not Found', 'ASSET_NOT_FOUND')] });
    renderApp(COMPARE);

    expect(await screen.findByText('Asset not found')).toBeVisible();
  });
});
