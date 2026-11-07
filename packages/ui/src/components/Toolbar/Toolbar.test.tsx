import { render, screen, within } from '@testing-library/react';

import { Toolbar } from '#ui/components/Toolbar/Toolbar';

describe('Toolbar', () => {
  it('groups its controls under a name, with the trailing ones at the end', () => {
    render(
      <Toolbar label="Gallery options" end={<button type="button">Sort</button>}>
        <h1>Assets</h1>
      </Toolbar>,
    );

    const toolbar = screen.getByRole('group', { name: 'Gallery options' });
    expect(within(toolbar).getByRole('heading', { name: 'Assets' })).toBeInTheDocument();
    expect(within(toolbar).getByRole('button', { name: 'Sort' }).parentElement).toHaveClass(
      'toolbar__end',
    );
  });

  it('has no trailing cluster without trailing controls', () => {
    const { container } = render(<Toolbar label="Options">Title</Toolbar>);

    expect(container.querySelector('.toolbar__end')).not.toBeInTheDocument();
  });
});
