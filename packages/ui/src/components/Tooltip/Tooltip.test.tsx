import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Tooltip } from '#ui/components/Tooltip/Tooltip';
import { TooltipPlacement } from '#ui/enums/tooltip-placement.enum';

const renderTooltip = () =>
  render(
    <Tooltip content="sunset_matte_painting_v3.png" placement={TooltipPlacement.End}>
      <button type="button">sunset_mat…v3.png</button>
    </Tooltip>,
  );

describe('Tooltip', () => {
  it('repeats the trigger text visually and keeps it out of the accessibility tree', () => {
    const { container } = renderTooltip();

    const bubble = screen.getByRole('tooltip', { hidden: true });
    expect(bubble).toHaveTextContent('sunset_matte_painting_v3.png');
    expect(bubble).toHaveAttribute('aria-hidden', 'true');
    expect(container.firstElementChild).toHaveClass('tooltip', 'tooltip--end');
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });

  it('is dismissed with Escape without moving focus, and comes back on the next hover', async () => {
    const { container } = renderTooltip();
    const trigger = screen.getByRole('button');

    await userEvent.tab();
    expect(trigger).toHaveFocus();
    await userEvent.keyboard('{Escape}');
    expect(container.firstElementChild).toHaveClass('tooltip--dismissed');
    expect(trigger).toHaveFocus();

    fireEvent.pointerLeave(container.firstElementChild as Element);
    expect(container.firstElementChild).not.toHaveClass('tooltip--dismissed');
  });

  it('comes back after the trigger loses focus', async () => {
    const { container } = renderTooltip();

    await userEvent.tab();
    await userEvent.keyboard('{Escape}');
    await userEvent.tab();

    expect(container.firstElementChild).not.toHaveClass('tooltip--dismissed');
  });

  it('can stretch to its container, for a truncated name', () => {
    const { container } = render(
      <Tooltip content="full name" isBlock>
        <span>full…</span>
      </Tooltip>,
    );

    expect(container.firstElementChild).toHaveClass('tooltip--block', 'tooltip--top');
  });

  it('wraps block content such as a heading in a div', () => {
    const { container } = render(
      <Tooltip content="rock_cliff_albedo" isBlock as="div">
        <h2>rock_cliff_albedo</h2>
      </Tooltip>,
    );

    expect(container.firstElementChild?.tagName).toBe('DIV');
  });
});
