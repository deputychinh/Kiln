import { render, screen } from '@testing-library/react';

import { ListDetail } from '@/components/ListDetail/ListDetail';
import { setViewportExpanded } from '@/test/viewport';

describe('ListDetail', () => {
  it('marks the layout by whether an item is selected and labels the detail pane', () => {
    const { container, rerender } = render(
      <ListDetail list="grid" detail="pane" hasSelection={false} detailLabel="Asset details" />,
    );
    expect(container.firstElementChild).toHaveClass('list-detail--list');

    rerender(<ListDetail list="grid" detail="pane" hasSelection detailLabel="Asset details" />);
    expect(container.firstElementChild).toHaveClass('list-detail--detail');
    expect(screen.getByRole('region', { name: 'Asset details' })).toHaveTextContent('pane');
  });

  it('makes the detail pane a tab stop only when expanded, where it scrolls on its own', () => {
    const { rerender } = render(
      <ListDetail list="grid" detail="pane" hasSelection detailLabel="Asset details" />,
    );
    expect(screen.getByRole('region', { name: 'Asset details' })).not.toHaveAttribute('tabindex');

    setViewportExpanded(true);
    rerender(
      <ListDetail list="grid" detail="pane" hasSelection={false} detailLabel="Asset details" />,
    );
    expect(screen.getByRole('region', { name: 'Asset details' })).toHaveAttribute('tabindex', '0');
  });
});
