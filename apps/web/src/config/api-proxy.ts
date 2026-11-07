import type { IncomingPeer, ProxiedRequest } from '@/interfaces/api-proxy.interface';

/** Headers a browser could send to pose as another address; the proxy never passes them on. */
const SPOOFABLE = ['forwarded', 'x-forwarded-for', 'x-real-ip'] as const;

/**
 * Vite's dev and preview proxy: `X-Forwarded-For` is the real peer of this hop, never what the
 * browser sent, so an API that trusts this proxy (`KILN_TRUSTED_PROXIES`) throttles sign-in by the
 * right address (KILN-12 review).
 */
export const forwardRealPeer = (outgoing: ProxiedRequest, incoming: IncomingPeer): void => {
  SPOOFABLE.forEach((name) => outgoing.removeHeader(name));
  const peer = incoming.socket.remoteAddress;
  if (peer) outgoing.setHeader('X-Forwarded-For', peer);
};
