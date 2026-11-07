# ADR 0014: Proxy headers only from trusted proxies

- Status: accepted · 2026-11-08 · Supersedes the reverse-proxy consequence of ADR 0013

## Context

ADR 0013 said that behind a reverse proxy uvicorn "must run with `--proxy-headers` and a forwarded-allow list". The KILN-12 review found the opposite risk: uvicorn reads `X-Forwarded-For` by default and believes it from 127.0.0.1, so any caller reaching the API over loopback (the Vite dev proxy, a reverse proxy on the same host, a shell on the box) chose the client address that sign-in throttling counts. A forged `X-Forwarded-For: 203.0.113.77` was recorded as the client.

## Decision

1. The API starts through `python -m kiln_api.serve` (`make api`, the e2e web server), never bare `uvicorn`. It passes uvicorn `proxy_headers=False` unless `KILN_TRUSTED_PROXIES` names proxies (comma-separated IPs or CIDRs); then `forwarded_allow_ips` is exactly that list.
2. Empty by default: the TCP peer is the client. A deployment behind a reverse proxy lists that proxy, or every client shares its address for throttling.
3. The Vite dev and preview proxy drops a browser's own `Forwarded`, `X-Forwarded-For` and `X-Real-IP` and sends its real peer, so trusting it never trusts the browser.

## Consequences

- `make api` and the README name the launcher; a bare `uvicorn kiln_api.main:app` reintroduces the risk.
- `test_a_forged_forwarded_for_does_not_choose_the_throttled_address` starts the real server process with a forged header; it fails with uvicorn's defaults.

## Sources

uvicorn settings (`--proxy-headers`, `--forwarded-allow-ips`, default `127.0.0.1`); OWASP Authentication Cheat Sheet (throttling by client); ADR 0013.
