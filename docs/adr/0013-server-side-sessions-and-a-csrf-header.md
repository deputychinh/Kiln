# ADR 0013: Server-side sessions on the app's origin, CSRF by header and Origin

- Status: accepted · 2026-11-08

## Context

KILN-12 signs people in with email and password. The web app ran on `:5173` and called the API on `127.0.0.1:8000`, a second origin: a cookie set by the API would be third-party whenever the page was opened at `localhost` (cross-site, so `SameSite=Lax` cookies are not sent on `fetch`). The CLI and Blender need credentials that are not cookies.

## Decision

1. **Opaque, server-side sessions in Postgres.** The cookie holds 256 random bits; the table holds only their SHA-256 (a database leak gives no live session). 30 minutes idle and 8 hours absolute (OWASP Session Management: 15–30 min idle for low-risk apps, an absolute bound of a working day); a new id at every sign-in, the old session deleted (fixation); sign-out deletes the row and clears the cookie. Last-seen is written at most once a minute. No JWT: revocation and expiry must take effect at once.
2. **Cookie flags.** `HttpOnly`, `SameSite=Lax`, `Path=/`, no `Domain`, `Max-Age` = 8 h; over HTTPS (`KILN_ENV=production` or `KILN_SECURE_COOKIES=true`) `Secure` and the `__Host-` prefix (`__Host-kiln_session`). On local http the cookie is `kiln_session` without `Secure`, which browsers would otherwise drop.
3. **Same origin.** The browser calls `/api/v1/…` on its own origin; Vite's dev and preview servers proxy `/api` to the API (`KILN_API_PROXY_TARGET`), and a deployment puts both behind one origin. `VITE_KILN_API_URL` is empty by default.
4. **CSRF: custom header + Origin, not double-submit.** Every cookie-authenticated request that is not GET/HEAD/OPTIONS — and sign-in and sign-out themselves (login CSRF) — needs `X-Kiln-Csrf: 1` and an `Origin` in `KILN_CORS_ORIGINS`; when a browser sends no `Origin`, `Sec-Fetch-Site` must be `same-origin`. The OWASP CSRF Prevention Cheat Sheet calls a custom request header "particularly well suited for AJAX or API endpoints": a cross-site page can only add it after a CORS preflight, which the API refuses for origins it does not list. It asks to verify `Origin` against the target origin and to fall back to standard headers when using Fetch Metadata, and treats `SameSite` as defence in depth, not the defence. Double-submit was rejected: the naive form is "discouraged" (cookie injection from a sibling subdomain), and the signed form adds a secret, a token endpoint and a second cookie for no gain over a header the SPA always sends.
5. **Bearer tokens skip the CSRF check** (they are not ambient credentials) and win over a cookie when both are sent; a bad token is 401 even next to a valid cookie.

## Consequences

- One origin in every deployment, or the cookie stops being first-party; `KILN_CORS_ORIGINS` doubles as the CSRF allow-list and must list the app's origin.
- Behind a reverse proxy, uvicorn must run with `--proxy-headers` and a forwarded-allow list, or every client shares the proxy's IP for sign-in throttling.
- A stolen session cookie works until idle, absolute expiry or sign-out; `HttpOnly` and no inline script keep it out of page scripts.

## Sources

[OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html), [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html), RFC 6265bis (cookie prefixes, SameSite), OWASP ASVS 5.0 V7 Session Management.
