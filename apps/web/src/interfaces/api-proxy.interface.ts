/** The part of Node's proxied (outgoing) request the forwarding rule touches. */
export interface ProxiedRequest {
  setHeader: (name: string, value: string) => unknown;
  removeHeader: (name: string) => unknown;
}

/** The part of the browser's (incoming) request the forwarding rule reads. */
export interface IncomingPeer {
  socket: { remoteAddress?: string | undefined };
}
