import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ApiStatus } from '@/features/health/components/ApiStatus';

const renderStatus = (): void => {
  const client = new QueryClient();
  render(
    <QueryClientProvider client={client}>
      <ApiStatus />
    </QueryClientProvider>,
  );
};

const respond = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

describe('ApiStatus', () => {
  afterEach(() => vi.restoreAllMocks());

  it('says it is checking, then shows the API version', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(respond({ status: 'ok', version: '0.0.0' }));
    renderStatus();

    expect(screen.getByRole('status')).toHaveTextContent('Checking the API');
    expect(await screen.findByText('API online · v0.0.0')).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith('http://api.test/health');
  });

  it('shows an error with a retry that asks again', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(respond({}, 503))
      .mockResolvedValueOnce(respond({ status: 'ok', version: '0.0.0' }));
    renderStatus();

    expect(await screen.findByRole('alert')).toHaveTextContent('The API is not reachable.');
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));

    expect(await screen.findByText('API online · v0.0.0')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
