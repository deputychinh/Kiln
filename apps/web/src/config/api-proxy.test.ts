import { forwardRealPeer } from '@/config/api-proxy';

const outgoing = () => {
  const headers = new Map<string, string>([
    ['x-forwarded-for', '203.0.113.77'],
    ['forwarded', 'for=203.0.113.77'],
    ['x-real-ip', '203.0.113.77'],
  ]);
  return {
    headers,
    setHeader: (name: string, value: string) => headers.set(name.toLowerCase(), value),
    removeHeader: (name: string) => headers.delete(name.toLowerCase()),
  };
};

describe('forwardRealPeer', () => {
  it('replaces a forged X-Forwarded-For with the real peer and drops the other forms', () => {
    const request = outgoing();

    forwardRealPeer(request, { socket: { remoteAddress: '::1' } });

    expect(Object.fromEntries(request.headers)).toEqual({ 'x-forwarded-for': '::1' });
  });

  it('sends no forwarding header when the peer is unknown', () => {
    const request = outgoing();

    forwardRealPeer(request, { socket: {} });

    expect(request.headers.size).toBe(0);
  });
});
