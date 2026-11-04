# KILN-3: Upload through presigned POST and confirm the upload

- Release: v0.1 · Status: todo (BA done) · Owner: Claude (deliver-loop)

## Story

As a **studio artist**, I want to send a file straight to storage and have Kiln confirm it arrived intact, so that large textures and meshes upload quickly and nobody reviews a half-uploaded file.

INVEST: Independent ☑ (builds on KILN-2 only) · Negotiable ☑ · Valuable ☑ · Estimable ☑ · Small ☑ (API + storage adapter, no UI) · Testable ☑

## Acceptance criteria

| Id             | Given                                                                                        | When                                                                    | Then                                                                                                                                                            |
| -------------- | -------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1            | a valid name, file name, content type and size                                               | `POST /api/v1/assets`                                                   | `201` with `Location: /api/v1/assets/{id}`, the asset, version 1 (`pending_upload`) and an `upload` object: `url`, form `fields`, `expires_at` 15 minutes ahead |
| AC2            | the `upload` object from AC1                                                                 | the client POSTs the file as multipart form data to `url` with `fields` | storage accepts it; the policy pins the object key, the content type and a size window of exactly the declared size                                             |
| AC3            | an uploaded object                                                                           | `POST /api/v1/asset-versions/{id}/completions`                          | `200`, the version is `processing`; calling it again returns `200` with the same version (idempotent)                                                           |
| AC4 (negative) | nothing was uploaded for the version                                                         | completion is requested                                                 | `409` with `UPLOAD_NOT_FOUND`; the version stays `pending_upload`                                                                                               |
| AC5 (negative) | an object whose size or content type differs from the declaration                            | completion is requested                                                 | `409` with `UPLOAD_MISMATCH`; the version stays `pending_upload`                                                                                                |
| AC6            | an existing asset                                                                            | `POST /api/v1/assets/{id}/versions` with a file of the same kind        | `201`, the next version number and its own `upload` object                                                                                                      |
| AC7            | assets exist                                                                                 | `GET /api/v1/assets?limit=&cursor=` and `GET /api/v1/assets/{id}`       | newest-first page `{items, next_cursor}`; the detail includes `versions` by number                                                                              |
| AC8 (negative) | an invalid body (missing field, wrong type) or a domain rule broken (name, type, size, kind) | any of the POSTs                                                        | `422` problem details with the KILN-2 error codes; nothing is stored                                                                                            |
| AC9 (negative) | an unknown asset or version id, or a malformed UUID                                          | any endpoint                                                            | `404` with `ASSET_NOT_FOUND` / `ASSET_VERSION_NOT_FOUND`, or `422` for a malformed id                                                                           |
| AC10           | the API starts against an empty storage server                                               | start-up                                                                | the bucket is created if it is missing; a storage outage makes `/ready` report `503` while `/health` stays `200`                                                |

## Non-functional

- Security (A01, A05, A06, A10): object keys come only from the server; the POST policy limits key, type and size; URLs expire after 15 minutes; completion re-checks size and type with `HEAD` (defence in depth if a storage server ignores a policy condition); JSON bodies limited to 1 MB by validation of field lengths.
- Reliability: storage calls have a 10 s timeout and surface `STORAGE_UNAVAILABLE` (`503`) instead of hanging; completion is idempotent.
- API (Zalando, RFC 9457): plural kebab-case resources, `201 + Location`, actions as sub-resources (`/completions`), `snake_case` JSON, problem details for every error, OpenAPI regenerated and web types updated.
- Performance: the API never proxies file bytes.

## Out of scope

- `Idempotency-Key` replay for `POST /assets` (filed as KILN-21), jobs and thumbnails (KILN-4), browser upload UI and bucket CORS (KILN-6), auth (KILN-12), multipart uploads above 500 MB.

## References

- AWS S3 — browser-based uploads with POST and policy conditions (`content-length-range`, `starts-with`): https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-HTTPPOSTConstructPolicy.html
- How to use S3 POST signed URLs (why POST over PUT for size limits): https://advancedweb.hu/how-to-use-s3-post-signed-urls/
- Zalando RESTful API Guidelines — 201 with Location, actions as sub-resources: https://opensource.zalando.com/restful-api-guidelines/
- RFC 9457 Problem Details; `references/api-design.md`, `references/security.md` (A10 limits), `references/data-and-reliability.md` (timeouts).

## Design

- **Port** `ObjectStorage` (`ports.py`): `ensure_bucket()`, `presign_upload(key, content_type, size_bytes, expires_in) -> PresignedUpload`, `head(key) -> StoredObject | None`, `ping()`. Adapter `adapters/s3_storage.py` with boto3 (SigV4, path-style, 10 s connect/read timeouts). Fake in `tests/fakes.py`. The database engine is built in `container.py` with `lock_timeout = 5s` and `statement_timeout = 15s` so the `FOR UPDATE` path cannot hang (KILN-2 review).
- **Service** `services/assets.py` (`AssetService`): `create`, `add_version`, `complete_upload`, `get`, `list` — the only place that combines repository, storage and clock.
- **Routes** `routes/assets.py`, schemas in `schemas/assets.py` (pydantic, boundary only); composition in `container.py` with FastAPI dependencies so tests swap fakes.
- **New error codes**: `UPLOAD_NOT_FOUND`, `UPLOAD_MISMATCH` (409), `STORAGE_UNAVAILABLE` (503).
- **Tests**: service unit tests with fakes; API tests through `TestClient` with fakes; one integration test against SeaweedFS (real POST upload, then completion, then an oversized POST to record whether the policy is enforced).

### Spike result (2026-11-04)

Probed SeaweedFS 4.48 with a boto3 presigned POST: exact size → `204`; one byte more → `400 EntityTooLarge`; one byte less → `400 EntityTooSmall`; another content type → `403 AccessDenied`; another key → `403`. Only the conforming object was stored. The policy is enforced, so the completion `HEAD` check stays as defence in depth (other S3 servers may differ), not as the primary control.
