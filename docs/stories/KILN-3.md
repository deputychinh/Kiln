# KILN-3: Upload through presigned POST and confirm the upload

- Release: v0.1 · Status: doing · Owner: Claude (deliver-loop)

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
| AC6            | an existing asset                                                                            | `POST /api/v1/assets/{id}/versions` with a file of the same kind        | `201`, the next version number, its own `upload` object and `Location: /api/v1/asset-versions/{id}`, which `GET` returns                                        |
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

### Design as built

- `adapters.py` (`S3ObjectStorage`, boto3), `services/assets.py` (`AssetService`), `schemas/assets.py`, `routes/assets.py`, `container.py` (engine with `lock_timeout` 5 s and `statement_timeout` 15 s, `pool_pre_ping`; S3 client with 10 s timeouts and 2 attempts), app lifespan creates the bucket and only warns if storage is down.
- The port signs with a TTL (`SignedPost`); the service owns `expires_at` through the `Clock`.
- `GET /api/v1/asset-versions/{id}` was added so the `Location` of a new version resolves.
- CORS allows `GET`/`POST` only and exposes `Location` and `X-Request-Id`.
- SeaweedFS reserves volumes per bucket, so integration tests share one `kiln-test` bucket and compose sizes volumes at 64 MB with `-volume.max=0`; the storage service has a `/healthz` healthcheck.

## QA

| AC   | Test(s)                                                                                                                                                                                                                                                                                                                                                                                                                                                         | Result |
| ---- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| AC1  | `api/test_assets_api.py::test_creating_an_asset_returns_version_one_and_a_signed_upload` (Location, 15-minute expiry from the clock, key/type/size/TTL passed to signing, no `object_key` leak)                                                                                                                                                                                                                                                                 | pass   |
| AC2  | `unit/test_s3_adapter.py::test_a_signed_post_pins_key_type_and_exact_size` (policy decoded), `integration/test_s3_storage.py::test_a_file_posted_with_the_signed_form_completes`, `::test_storage_rejects_a_body_of_another_size` (65 → `EntityTooLarge`, 63 → `EntityTooSmall`), `::test_storage_rejects_another_content_type` (403)                                                                                                                           | pass   |
| AC3  | `api/…::test_completing_an_upload_starts_processing_and_is_idempotent`, `::test_a_completion_that_loses_a_race_returns_the_winner_s_result`                                                                                                                                                                                                                                                                                                                     | pass   |
| AC4  | `api/…::test_completing_without_an_upload_is_a_conflict`                                                                                                                                                                                                                                                                                                                                                                                                        | pass   |
| AC5  | `api/…::test_completing_a_mismatched_upload_is_a_conflict` (size −1, +1, other type)                                                                                                                                                                                                                                                                                                                                                                            | pass   |
| AC6  | `api/…::test_adding_a_version_returns_the_next_number_and_its_own_upload`, `::test_a_version_of_another_kind_is_rejected`                                                                                                                                                                                                                                                                                                                                       | pass   |
| AC7  | `api/…::test_listing_pages_newest_first_and_detail_lists_versions`, `::test_a_malformed_cursor_is_a_400`                                                                                                                                                                                                                                                                                                                                                        | pass   |
| AC8  | `api/…::test_invalid_creations_are_rejected_and_nothing_is_stored` (8: blank name, GIF, size 0, `..`, missing field, wrong type, extra field, 1001-character name)                                                                                                                                                                                                                                                                                              | pass   |
| AC9  | `api/…::test_unknown_ids_are_404_with_a_stable_code` (4 endpoints), `::test_a_malformed_id_is_a_validation_error`                                                                                                                                                                                                                                                                                                                                               | pass   |
| AC10 | `api/test_health.py::test_ready_checks_database_and_storage_and_creates_the_bucket`, `::test_a_storage_outage_makes_ready_fail_while_health_stays_up`, `api/test_dependencies.py` (database outage → `503 DATABASE_UNAVAILABLE`; start-up with storage down logs a warning), `unit/test_s3_adapter.py` (missing bucket created; 403, failed creation and 500 → `STORAGE_UNAVAILABLE`), `integration/…::test_an_unreachable_endpoint_raises_storage_unavailable` | pass   |

Contract: `unit/test_openapi_contract.py` (2) keeps `openapi.json` equal to the app; web types regenerated with `make openapi`.

Exploratory and mutation checks: removing the size/type comparison in `complete_upload` → 3 tests fail; removing `content-length-range` from the policy → 3 tests fail (both restored). Equivalence classes for completion (no object, smaller, larger, other type, exact); boundary of the policy size (±1 byte) on the real server; error guessing: duplicate completion, a concurrent completion winning first, storage down at start-up and during a request, unreachable database, malformed UUID and cursor, unknown fields.

Defect found in QA and fixed: a bucket per integration test exhausted SeaweedFS volumes ("No writable volumes and no free volumes left") and storage returned `500`; tests now share one bucket and compose sizes volumes.

Gates: `make ci` green — Python 181 passed, coverage 99 %; ruff and mypy strict clean; web e2e 4/4 on the production build. Counts from `pytest --collect-only`: `test_assets_api.py` 26, `test_health.py` 5, `test_dependencies.py` 2, `test_s3_adapter.py` 6, `test_s3_storage.py` 6, `test_openapi_contract.py` 2.

## Review score

_Pending independent review._
