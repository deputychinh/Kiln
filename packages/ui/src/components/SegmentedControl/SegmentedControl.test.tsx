import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { SegmentedControl } from '#ui/components/SegmentedControl/SegmentedControl';

const OPTIONS = [
  { value: 'all', label: 'All' },
  { value: 'image', label: 'Images', icon: <svg /> },
  { value: 'model', label: 'Models', isDisabled: true },
];

describe('SegmentedControl', () => {
  it('is a named group of radio buttons with the current choice checked', () => {
    render(
      <SegmentedControl
        label="Kind"
        name="kind"
        value="image"
        options={OPTIONS}
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByRole('group', { name: 'Kind' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Images' })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'All' })).not.toBeChecked();
    expect(screen.getByRole('radio', { name: 'Models' })).toBeDisabled();
  });

  it('reports a new choice, by pointer or with the arrow keys', async () => {
    const onChange = vi.fn();
    render(
      <SegmentedControl
        label="Kind"
        name="kind"
        value="all"
        options={OPTIONS}
        onChange={onChange}
      />,
    );

    await userEvent.click(screen.getByRole('radio', { name: 'Images' }));
    expect(onChange).toHaveBeenLastCalledWith('image');

    screen.getByRole('radio', { name: 'All' }).focus();
    await userEvent.keyboard('{ArrowRight}');
    expect(onChange).toHaveBeenLastCalledWith('image');
  });

  it('keeps the labels as accessible names when only icons show', () => {
    render(
      <SegmentedControl
        label="Card size"
        isLabelHidden
        isIconOnly
        name="size"
        value="all"
        options={OPTIONS}
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByRole('radio', { name: 'Images' })).toBeInTheDocument();
    expect(screen.getByText('Images')).toHaveClass('segmented-control__text--hidden');
    expect(screen.getByText('Card size')).toHaveClass('segmented-control__legend--hidden');
  });
});
