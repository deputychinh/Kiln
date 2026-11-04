# KILN-21: Idempotency-Key for creating assets and versions

- Release: v0.1 · Status: doing · Owner: Claude (deliver-loop)

## Story

As an **artist on a flaky studio network** (or the Blender add-on and CLI retrying for me), I want to resend a "create asset" or "add version" request safely, so that a timeout never leaves me with duplicate assets or version numbers I did not intend.

INVEST: Independent ☑ (builds on KILN-3) · Negotiable ☑ · Valuable ☑ · Estimable ☑ · Small ☑ (one table, one middleware-like helper, two endpoints) · Testable ☑

## Acceptance criteria

| Id                | Given                                                                                                          | When                                                         | Then                                                                                                                                                                                                                         |
| ----------------- | -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1               | a `POST /api/v1/assets` with header `Idempotency-Key: "<uuid>"` that succeeded                                 | the same request with the same key is sent again within 24 h | `201` with the same asset and version ids and the same `Location`, header `Idempotent-Replayed: true`, a freshly signed `upload` form (signatures are not side effects), and no second asset exists                          |
| AC2               | the same as AC1 for `POST /api/v1/assets/{id}/versions`                                                        | resent                                                       | the same version number is returned; no extra version is created                                                                                                                                                             |
| AC3 (negative)    | a key already used with a different body or a different path                                                   | the request is sent                                          | `422` problem details with `IDEMPOTENCY_KEY_REUSED`; nothing is created                                                                                                                                                      |
| AC4 (concurrency) | a request with the key is still in progress                                                                    | a duplicate arrives                                          | it waits for the first one (the key row is locked in the same transaction) and then gets the replay of AC1/AC2; if it waits longer than the lock timeout it gets `409` with `IDEMPOTENCY_KEY_IN_USE` and may retry unchanged |
| AC5 (edge)        | a header that is not a valid key (empty, over 255 characters, non-printable characters, a malformed sf-string) | any of the two POSTs                                         | `400` with `INVALID_IDEMPOTENCY_KEY`                                                                                                                                                                                         |
| AC6               | no `Idempotency-Key` header                                                                                    | any of the two POSTs                                         | the request is processed normally (the key is optional in v0.1; the CLI and add-on always send one)                                                                                                                          |
| AC7               | a request with a key that failed with a client error (4xx from validation or a domain rule)                    | the corrected request is sent with the same key              | it is processed as new (failures are not stored), so a client can fix and retry                                                                                                                                              |
| AC8               | a key older than 24 h                                                                                          | reused                                                       | it is treated as new; expired keys are purged by the purge function (scheduled by the worker in KILN-4)                                                                                                                      |

## Non-functional

- Reliability: the key row and the created asset/version are written in **one transaction**, so a crash cannot store one without the other; concurrent duplicates are serialised by the primary key `(scope, key)`.
- Security: keys are scoped by method + path, and in v0.2 by principal (KILN-12), so one client cannot replay another's response; request bodies are stored only as a SHA-256 hash; stored responses contain no secrets (the signed form is regenerated, never stored).
- API: header syntax per the IETF draft (an sf-string, e.g. `"8e03978e-40d5-43e8-bc93-6894a57f9324"`); unquoted tokens are accepted for tolerance; the expiry policy (24 h) is published in the OpenAPI description.

## Out of scope

- Requiring the key (v0.2 once clients send it), idempotency for completions (already idempotent by state), scheduling the purge (KILN-4).

## References

- IETF draft-ietf-httpapi-idempotency-key-header-08 (22 Oct 2026): 400 for a missing/invalid key, 422 for reuse with a different payload, 409 while the first request is in progress, sf-string syntax, published expiry: https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/
- Vendor practice (Ripple, Gotitus): replay the original status and body; do not cache failures so clients can correct and retry: https://docs.ripple.com/products/collections/guides/idempotency, https://docs.gotitus.com/guide/developer-resources/idempotency
- `references/api-design.md` (idempotency MUST), `references/data-and-reliability.md` (one transaction per use case).

## Design decision

The IETF draft says a duplicate of an in-progress request SHOULD get `409`. Kiln writes the key and the asset in **one transaction**, so a duplicate blocks on the uncommitted key row and receives the replay once the first commits — better for clients than a 409 they must retry. `409 IDEMPOTENCY_KEY_IN_USE` remains for the case where the wait exceeds `lock_timeout` (SQLSTATE 55P03 on the key row).

## Design

- **Table** `idempotency_keys(scope text, key text, request_hash bytea(32), status_code int, response jsonb, created_at timestamptz, PRIMARY KEY (scope, key))`, migration `0002_idempotency_keys`, index on `created_at` for the purge.
- **Flow** (service layer, one transaction with the creation): `INSERT … ON CONFLICT DO NOTHING` a row marked in progress (`status_code` NULL); on conflict, read the row: different hash → 422; `status_code` NULL → 409; else replay. On success, store status and response body (without `upload`), commit together with the asset. On a domain error the transaction rolls back, so the key is not stored (AC7).
- **Replay**: rebuild the response from the stored ids (re-read asset and version) and sign a new upload form.
- **Port** `IdempotencyStore` with a Postgres adapter; the repository and the store share one connection per use case via a unit-of-work.

### Design as built

- `domain/idempotency.py`: `parse_idempotency_key` (RFC 9651 sf-string with `\"`/`\\` escapes, or a bare token; 1–255 printable ASCII) and `request_fingerprint` (SHA-256 of the operation and the canonical JSON payload).
- Table `idempotency_keys(key PK, operation, request_hash bytea(32), asset_id, version_id, created_at)` with an index on `created_at` (migration `0002_idempotency_keys`). The key is the primary key on its own, so reusing it on another endpoint gives a different fingerprint and `422`.
- `repositories/unit_of_work.py` (`SqlUnitOfWork`) hands out an `SqlAssetRepository` and an `SqlIdempotencyStore` bound to one connection; `SqlAssetRepository` now accepts an `Engine` (one transaction per call) or a `Connection` (joins the caller's).
- `SqlIdempotencyStore.claim`: delete the key if older than 24 h, `INSERT … ON CONFLICT DO NOTHING RETURNING`, otherwise read the committed row; a lock wait past `lock_timeout` (SQLSTATE 55P03) → `IDEMPOTENCY_KEY_IN_USE`. `purge_expired_keys(engine, now)` is ready for the worker (KILN-4).
- `AssetService.create/add_version` run claim → create → complete in one unit of work; a replay re-reads the asset and version and signs a new upload form. Routes read the header through a dependency and set `Idempotent-Replayed: true` on replays.

## QA

| AC  | Test(s)                                                                                                                                                                                                             | Result |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| AC1 | `api/test_idempotency_api.py::test_a_retried_creation_replays_the_same_asset_with_a_fresh_upload` (same ids and Location, replay header, later expiry, one asset)                                                   | pass   |
| AC2 | `::test_a_retried_new_version_replays_the_same_number`                                                                                                                                                              | pass   |
| AC3 | `::test_a_key_reused_with_another_body_is_rejected`, `::test_a_key_reused_on_another_endpoint_is_rejected`, `unit/test_idempotency_key.py::test_the_fingerprint_depends_on_operation_and_payload_but_not_key_order` | pass   |
| AC4 | `::test_concurrent_duplicates_wait_and_all_get_the_same_asset` (6 threads, one asset), `::test_a_key_held_longer_than_the_lock_timeout_is_in_use` (409)                                                             | pass   |
| AC5 | `::test_an_invalid_key_is_a_400` (6), `unit/test_idempotency_key.py` (5 valid, 12 invalid forms)                                                                                                                    | pass   |
| AC6 | `::test_without_a_key_every_request_creates`                                                                                                                                                                        | pass   |
| AC7 | `::test_a_failed_request_does_not_store_the_key`                                                                                                                                                                    | pass   |
| AC8 | `::test_an_expired_key_is_treated_as_new`, `db/test_idempotency_store.py::test_purging_removes_only_keys_older_than_the_window`                                                                                     | pass   |

Guards: `unit/test_idempotency_guards.py` (a half-recorded key is never replayed; other database errors during a claim propagate; the OpenAPI schema is built once). Migration and schema drift: covered by the existing `db/test_migrations.py` (definitions compared with `schema.py`).

Mutation checks (`PYTHONDONTWRITEBYTECODE=1`, code restored each time), all killed: no fingerprint comparison (2 failed), no expiry (1), never completing the key (3), never replaying (5).

Counts from `pytest --collect-only`: `test_idempotency_key.py` 18, `test_idempotency_api.py` 15, `test_idempotency_store.py` 1, `test_idempotency_guards.py` 3; total suite 279.

Gates: `make ci` green — Python 286 passed, coverage 99 %; ruff and mypy strict clean.

### Review round 1 changes (8.0/10)

- OpenAPI: both creation endpoints document `400` and `409` problems and the `Idempotent-Replayed` header; the key parameter describes its limits.
- A key header sent twice is `400` (several lines form an sf-list, not one key).
- A replay after the version left `pending_upload` returns `upload: null` instead of a form that can no longer be used.
- New tests: the same key and body on two assets (`422`), crash between the asset insert and completing the key (both tables empty, retry creates), the exact 24 h boundary for claims and purges, the replay without a form, the duplicated header. The four surviving mutants of the review (no asset in the scope, repository on its own transaction, `<=` in claim and purge) are killed.
- ADR 0006 records waiting instead of an immediate `409` and the unit-of-work change; the purge is scheduled by KILN-22 (backlog).

## Review score

_Pending independent review._
