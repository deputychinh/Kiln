# ADR 0008: Preview URLs signed at the start of a time window, with botocore's own signer

- Status: accepted · 2026-11-06

## Context

Browsers cache images by URL. boto3's `generate_presigned_url` signs at the current second (`SigV4Auth.add_auth` reads `get_current_datetime()`, with no parameter to pass a time), so every API response carried a new URL for every preview and nothing was ever reused (KILN-6 debt, KILN-27). Options: a CDN or public bucket (out of scope for v0.1, and previews are studio IP), a redirect endpoint in the API (one more round trip per image and the API in the image path), patching botocore's module clock (process-wide, not thread-safe), a hand-written SigV4 signer, or botocore's signer with its timestamp pinned.

A first implementation hand-wrote SigV4. It matched boto3 for plain endpoints but diverged for endpoints boto3 accepts (a path prefix, a default port, an upper-case host), failing silently with 403 previews, and it went against the house rule "no home-made crypto" (`references/security.md`, A04).

## Decision

1. **Sign with botocore's `S3SigV4QueryAuth`**, subclassed only to set `request.context["timestamp"]` in `_modify_request_before_signing` (the hook `add_auth` calls right after stamping the current time). Canonicalisation, host normalisation and the HMAC chain stay botocore's (`kiln_api/signing.py`). Tests cross-check the URL against boto3's with its clock frozen, for odd keys, regions, access keys, time zones and endpoint shapes.
2. **Sign at the start of a 10-minute window, valid 25 minutes** (`DOWNLOAD_URL_WINDOW_SECONDS`, `DOWNLOAD_URL_LIFETIME_SECONDS` = 15-minute TTL + window): one URL per preview per window, at least 15 minutes left when handed out, never more than 25 minutes after the window began.
3. **`response-cache-control: private, max-age=1500, immutable`** in the signed URL: storage returns it, the browser keeps the image privately; a version's thumbnail never changes, so `immutable` is safe. `max-age` counts from the download, so a cached copy can outlive its URL by up to 10 minutes; that is harmless because the expired URL is never requested again and the cache is private.

## Consequences

- Repeat views within a window cost no download; the API stays out of the image path; signing is still local (no network call) and passes through the storage circuit.
- Limits: path-style addressing; static access keys (no session token or role credentials — add `token` to `SigningCredentials` when deployment needs it); the endpoint must be an http(s) URL without credentials, query or fragment (checked at start-up).
- The pinned hook is a protected botocore method: a botocore upgrade that renames it fails the cross-check tests loudly rather than producing bad URLs.
- A leaked URL is valid for at most 25 minutes (was 15), for one GET of one key.
