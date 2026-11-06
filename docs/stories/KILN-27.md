# KILN-27: Stable signed preview URLs

- Release: v0.1 · Status: doing · Owner: Claude (deliver-loop)

## Story

As an **artist browsing the gallery**, I want previews I have already seen to come from my browser's cache, so that the gallery and the detail open instantly and do not download the same images again on every refresh.

Today every API response signs every preview URL at the current second, so the URL (the browser's cache key) changes on each request and nothing is reused (debt from KILN-6).

INVEST: Independent ☑ (API only; the web app keeps its URL handling) · Negotiable ☑ · Valuable ☑ · Estimable ☑ · Small ☑ · Testable ☑

## Acceptance criteria

| Id             | Given                                        | When                                                                                     | Then                                                                                                                                                                                                                 |
| -------------- | -------------------------------------------- | ---------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1            | a ready preview                              | the list or the detail is requested twice in the same 10-minute window (any API process) | both responses carry the identical URL for it                                                                                                                                                                        |
| AC2            | a URL handed out at any moment of its window | the browser loads it                                                                     | it is valid for at least 15 minutes after it was handed out and never longer than 25 minutes after its window began                                                                                                  |
| AC3            | a preview loaded once                        | the gallery is loaded again within the window                                            | storage answered with `Cache-Control: private, max-age=1500, immutable`, so the browser serves the image from its cache without a request                                                                            |
| AC4            | the next window starts                       | the list is requested                                                                    | the URL changes (a new signature); a URL past its 25 minutes is refused by storage                                                                                                                                   |
| AC5 (security) | any object key                               | a URL is signed                                                                          | the signature is AWS SigV4 exactly as boto3 would compute it at that time (cross-checked for plain, nested, space, unicode and reserved-character keys), the URL is a GET for one key only, and the cache is private |

## Non-functional

- Security: no new secret; URLs stay short-lived (25 min worst case instead of 15) and object-scoped; `private` keeps previews out of shared caches. Keys are still built by the server (UUIDs), never from user input.
- Performance: repeat views within a window cost no image download (LCP of a revisited gallery no longer waits on previews); signing stays local (no network call).
- Reliability: signing does not depend on the storage circuit (GuardedStorage passes it through, as before).

## Out of scope

- A CDN or public bucket for previews.
- Changing the web app's signed-URL handling (it already keeps a still-valid URL; stable URLs only make the cache hit).

## References

- AWS — Authenticating requests: query parameters (SigV4 presigned URLs), `response-cache-control` override: https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-query-string-auth.html , https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetObject.html
- RFC 9111 HTTP Caching (`private`, `max-age`) and RFC 8246 `immutable`.
- web.dev — HTTP cache: https://web.dev/articles/http-cache
- `references/data-and-reliability.md` (caching), `references/security.md` (short-lived signed URLs).

## Design

- `kiln_api/signing.py`: botocore's `S3SigV4QueryAuth` with its signing time pinned (`presign_get_url`), cross-checked against boto3 with its clock frozen (ADR 0008).
- Port: `ObjectStorage.presign_download(key, *, signed_at, ttl_seconds)`; the S3 adapter signs with the pure signer (credentials from settings) and adds `response-cache-control`.
- Service: previews are signed at the start of the current 10-minute window (`DOWNLOAD_URL_WINDOW_SECONDS`) for 25 minutes (`DOWNLOAD_URL_TTL_SECONDS` 15 + window), with `Cache-Control: private, max-age=1500, immutable` (the thumbnail of a version never changes).
- Web: no change in behaviour; comments that pointed at KILN-27 are updated.

## QA

| AC  | Test(s)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | Result |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------ |
| AC1 | `test_a_preview_url_stays_the_same_for_its_window_and_changes_with_the_next` (detail and list, first and last second of a window); integration `test_a_signed_get_is_stable_cacheable_and_expires` (two separately built storages give the same URL)                                                                                                                                                                                                                                                                                                                                 | pass   |
| AC2 | `test_a_preview_url_lives_25_minutes_and_is_privately_cacheable` (handed out in the window's last second: ≥ 15 min left, 25 min from the window start)                                                                                                                                                                                                                                                                                                                                                                                                                               | pass   |
| AC3 | integration: SeaweedFS answers `Cache-Control: private, max-age=1500, immutable`; e2e `gallery.spec.ts` "a preview seen once comes from the browser cache…": the first image response carries that header (mutation: no header → fails), and two page loads 2 s apart give the same `src` with `transferSize` 0, on desktop and mobile                                                                                                                                                                                                                                               | pass   |
| AC4 | API test: the next window gives another URL; integration: a URL signed an hour ago for 60 s is refused (403)                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | pass   |
| AC5 | `tests/unit/test_signing.py`: the URL equals boto3's at the same instant (frozen clock) for 5 keys × with/without cache control and for endpoints with a path prefix, a default port and an upper-case host (region eu-west-3, an access key with `/` and `+`); a time in another zone signs as the same UTC instant (23:55 at UTC−7 → next UTC day); same inputs → same URL; another instant or key → another signature; naive times, expiries outside 1–604800 s and endpoints with credentials, query, fragment or another scheme are refused; the secret never shows in a `repr` | pass   |

Mutation: signing at `clock.now()` instead of the window start fails the API test and the e2e (once the e2e spans more than one second; it waits 2 s and never straddles a window boundary).

## Review rounds

| Round | Score | Findings → fixes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| ----- | ----- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1     | 8.0   | The hand-written SigV4 signer diverged from boto3 for endpoints with a path prefix, a default port or an upper-case host (silent 403 previews) and went against "no home-made crypto" without an ADR → botocore's own `S3SigV4QueryAuth` with its timestamp pinned, ADR 0008, endpoint checks at start-up. The secret showed in `SigningCredentials`' repr → `repr=False`. No bounds on `expires_seconds` → 1–604800 s. A time-zone mutation survived → a non-UTC test. The e2e passed without the cache header → it asserts the header. |
