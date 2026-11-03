# Security

Target: OWASP ASVS 5.0 Level 1, following `references/security.md` (OWASP Top 10:2025).

## Threat model

| Asset                        | Entry point                     | Threat                                                       | Control                                                                                                                                                       |
| ---------------------------- | ------------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Studio files (IP)            | presigned URLs, download API    | leaked links, guessed ids                                    | short URL expiry; UUID v7 ids; per-object authorization before signing (A01)                                                                                  |
| Uploads                      | presigned PUT                   | malicious files, oversized files, `.glb` decompression bombs | sign with `Content-Type` and `content-length-range`; the worker checks magic bytes, caps decoded size and processing time, runs in its own process (A06, A10) |
| Accounts, CLI/Blender tokens | sign-in, `Authorization` header | password guessing, leaked tokens                             | Argon2id; throttling; 256-bit random tokens stored hashed and revocable (A04, A07)                                                                            |
| AI search                    | user text → model               | prompt injection to read other people's data                 | the model returns allow-listed filters only; authorization applies afterwards, in the API (A01, A05)                                                          |
| Claude spend                 | AI jobs                         | abuse that burns budget                                      | monthly budget, cache by file hash, per-user rate limit                                                                                                       |
| Supply chain                 | npm, PyPI, add-on               | malicious packages                                           | committed lockfiles, exact pins, `npm audit` in CI, `pip-audit` before each release (A03)                                                                     |

## Baseline

- Headers: CSP (no `unsafe-inline` scripts), HSTS, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`.
- CORS allow-list from `KILN_CORS_ORIGINS`.
- Limits: JSON body 1 MB; asset 500 MB; pagination `limit` at most 100.
- Security events (sign-in, authorization denial, token revocation) are logged with ids and without secrets.
- Secrets only in env; `.env` never enters git.
