import { render, screen, waitFor } from '@testing-library/react';

import { UploadStatus } from '@/enums/upload-status.enum';
import { UploadPageEffects } from '@/features/uploads/components/UploadPageEffects';
import { UploadPanel } from '@/features/uploads/components/UploadPanel';
import type { UploadItem } from '@/interfaces/upload.interface';
import { anItem, uploadsWith } from '@/test/upload-items';

/** The page's effects over a queue the test rerenders with new rows and outcomes. */
const Effects = ({ items, outcomes = [] }: { items: UploadItem[]; outcomes?: UploadItem[] }) => (
  <UploadPageEffects uploads={uploadsWith(items, outcomes)} />
);

const version = (overrides: Partial<UploadItem> = {}): UploadItem =>
  anItem({
    id: 'version-row',
    file: new File(['x'], 'rock_v2.png'),
    targetAssetId: 'asset-9',
    assetId: 'asset-9',
    ...overrides,
  });

describe('UploadPageEffects', () => {
  it('refuses a file dropped outside the zone instead of letting the browser open it', () => {
    render(<UploadPageEffects uploads={uploadsWith([])} />);

    const drop = new Event('drop', { bubbles: true, cancelable: true });
    Object.defineProperty(drop, 'dataTransfer', {
      value: { types: ['Files'], dropEffect: 'copy' },
    });
    document.body.dispatchEvent(drop);
    const text = new Event('drop', { bubbles: true, cancelable: true });
    Object.defineProperty(text, 'dataTransfer', { value: { types: ['text/plain'] } });
    document.body.dispatchEvent(text);

    expect(drop.defaultPrevented).toBe(true);
    expect(text.defaultPrevented).toBe(false);
  });

  it('asks before the page is left while files are uploading, and not after', () => {
    const { rerender } = render(<Effects items={[anItem({ status: UploadStatus.Uploading })]} />);
    const busy = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(busy);
    expect(busy.defaultPrevented).toBe(true);

    rerender(<Effects items={[anItem({ status: UploadStatus.Ready })]} />);
    const idle = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(idle);
    expect(idle.defaultPrevented).toBe(false);
  });

  it('announces a repeated outcome again, outside the list pane', async () => {
    const ready = anItem({ status: UploadStatus.Ready });
    // Outcomes from before the panel mounted are not news; only later ones are announced.
    const { rerender } = render(<Effects items={[ready]} />);
    rerender(<Effects items={[ready]} outcomes={[ready]} />);
    const live = (await screen.findByText('rock.png: Ready.')).closest('[aria-live]');
    expect(live?.parentElement).toBe(document.body);

    rerender(<Effects items={[ready]} outcomes={[ready, { ...ready }]} />);
    expect(live).toHaveTextContent('');
    await waitFor(() => expect(live).toHaveTextContent('rock.png: Ready.'));
  });

  it('announces every outcome when files end in separate changes within one frame', async () => {
    const a = anItem({
      status: UploadStatus.Failed,
      error: 'Kiln is busy right now. Try again in a moment.',
    });
    const b = anItem({
      id: 'row-2',
      status: UploadStatus.Failed,
      error: 'This file is empty.',
      file: new File([], 'b.png'),
    });
    const c = anItem({
      id: 'row-3',
      status: UploadStatus.Processing,
      file: new File(['x'], 'c.png'),
    });
    const { rerender } = render(<Effects items={[a, b, c]} />);
    rerender(<Effects items={[a, b, c]} outcomes={[a]} />);
    rerender(<Effects items={[a, b, c]} outcomes={[a, b]} />);
    rerender(
      <Effects
        items={[a, b, { ...c, status: UploadStatus.Ready }]}
        outcomes={[a, b, { ...c, status: UploadStatus.Ready }]}
      />,
    );

    const live = document.body.querySelector('[aria-live="polite"]');
    await waitFor(() =>
      expect(live).toHaveTextContent(
        'rock.png: Kiln is busy right now. Try again in a moment. b.png: This file is empty. c.png: Ready.',
      ),
    );
  });

  it('announces the files that just ended, once, politely', async () => {
    const ready = anItem({ status: UploadStatus.Ready });
    const failed = anItem({
      id: 'row-2',
      status: UploadStatus.Failed,
      error: 'This file is empty.',
      file: new File([], 'empty.png'),
    });
    const { rerender } = render(<Effects items={[ready, failed]} />);
    rerender(<Effects items={[ready, failed]} outcomes={[ready, failed]} />);

    const live = (await screen.findByText(/rock.png: Ready/)).closest('[aria-live]');
    expect(live).toHaveAttribute('aria-live', 'polite');
    expect(live).toHaveTextContent('rock.png: Ready. empty.png: This file is empty.');
    expect(live?.textContent).not.toContain('..');
  });

  it('announces a version outcome once, even when its asset is not open', async () => {
    const running = version({ status: UploadStatus.Uploading });
    const ready = version({ status: UploadStatus.Ready });
    const uploads = uploadsWith([ready], [ready]);
    // The gallery panel and another asset's panel are on screen; neither shows this row.
    const { rerender } = render(
      <>
        <UploadPageEffects uploads={uploadsWith([running])} />
        <UploadPanel uploads={uploadsWith([running])} />
      </>,
    );
    rerender(
      <>
        <UploadPageEffects uploads={uploads} />
        <UploadPanel uploads={uploads} />
        <UploadPanel uploads={uploads} target={{ assetId: 'asset-3', kind: 'image' }} />
      </>,
    );

    await waitFor(() =>
      expect(document.body.querySelectorAll(':scope > [aria-live="polite"]')).toHaveLength(1),
    );
    const live = document.body.querySelector('[aria-live="polite"]');
    await waitFor(() => expect(live).toHaveTextContent('rock_v2.png: Ready.'));
    expect(live?.textContent).toBe('rock_v2.png: Ready.');
    expect(screen.queryByText('rock_v2.png')).not.toBeInTheDocument();
  });

  it('warns before the page is left while only a version is uploading', () => {
    render(<Effects items={[version({ status: UploadStatus.Uploading })]} />);

    const leaving = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(leaving);

    expect(leaving.defaultPrevented).toBe(true);
  });
});
