import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Tabs } from '#ui/components/Tabs/Tabs';

const TABS = [
  { id: 'versions', label: 'Versions', badge: 3, panel: <p>Version list</p> },
  { id: 'info', label: 'Info', panel: <p>Facts</p> },
  { id: 'tags', label: 'Tags', panel: <p>Tag list</p> },
];

describe('Tabs', () => {
  it('shows the first tab and its panel, with the others hidden and one tab stop', () => {
    render(<Tabs label="Asset sections" tabs={TABS} />);

    expect(screen.getByRole('tablist', { name: 'Asset sections' })).toBeInTheDocument();
    const versions = screen.getByRole('tab', { name: 'Versions 3' });
    expect(versions).toHaveAttribute('aria-selected', 'true');
    expect(versions).toHaveAttribute('tabindex', '0');
    expect(screen.getByRole('tab', { name: 'Info' })).toHaveAttribute('tabindex', '-1');
    expect(screen.getByRole('tabpanel', { name: 'Versions 3' })).toHaveTextContent('Version list');
    expect(screen.queryByText('Facts')).not.toBeVisible();
  });

  it('opens a tab when it is clicked', async () => {
    const onSelect = vi.fn();
    render(<Tabs label="Asset sections" tabs={TABS} onSelect={onSelect} />);

    await userEvent.click(screen.getByRole('tab', { name: 'Info' }));

    expect(screen.getByRole('tabpanel', { name: 'Info' })).toHaveTextContent('Facts');
    expect(onSelect).toHaveBeenCalledWith('info');
  });

  it('moves between tabs with the arrow keys, Home and End, wrapping round', async () => {
    render(<Tabs label="Asset sections" tabs={TABS} defaultSelectedId="info" />);

    await userEvent.tab();
    expect(screen.getByRole('tab', { name: 'Info' })).toHaveFocus();
    await userEvent.keyboard('{ArrowRight}');
    expect(screen.getByRole('tab', { name: 'Tags' })).toHaveFocus();
    expect(screen.getByRole('tab', { name: 'Tags' })).toHaveAttribute('aria-selected', 'true');
    await userEvent.keyboard('{ArrowRight}');
    expect(screen.getByRole('tab', { name: 'Versions 3' })).toHaveFocus();
    await userEvent.keyboard('{ArrowLeft}');
    expect(screen.getByRole('tab', { name: 'Tags' })).toHaveFocus();
    await userEvent.keyboard('{Home}');
    expect(screen.getByRole('tab', { name: 'Versions 3' })).toHaveFocus();
    await userEvent.keyboard('{End}');
    expect(screen.getByRole('tab', { name: 'Tags' })).toHaveFocus();
    await userEvent.keyboard('a');
    expect(screen.getByRole('tab', { name: 'Tags' })).toHaveFocus();
  });

  it('follows the selected tab when controlled', () => {
    const { rerender } = render(<Tabs label="Sections" tabs={TABS} selectedId="tags" />);
    expect(screen.getByRole('tab', { name: 'Tags' })).toHaveAttribute('aria-selected', 'true');

    rerender(<Tabs label="Sections" tabs={TABS} selectedId="info" />);
    expect(screen.getByRole('tab', { name: 'Info' })).toHaveAttribute('aria-selected', 'true');
  });
});
