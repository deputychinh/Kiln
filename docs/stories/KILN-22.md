# KILN-22: Scheduled maintenance in the worker

- Release: v0.1 · Status: doing · Owner: Claude (deliver-loop)

## Story

As the **person running a Kiln studio server**, I want abandoned uploads and expired idempotency keys cleaned up automatically, so that storage and the database do not grow with garbage and the gallery does not show versions "waiting for upload" forever.

INVEST: Independent ☑ (KILN-3/21/4 data only) · Negotiable ☑ · Valuable ☑ · Estimable ☑ · Small ☑ (three bounded sweeps, no UI beyond one failure reason) · Testable ☑

## Acceptance criteria

| Id                | Given                                                                                             | When                       | Then                                                                                                                                                                                                                                                                         |
| ----------------- | ------------------------------------------------------------------------------------------------- | -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1               | a version still `pending_upload` 24 h after it was created                                        | maintenance runs           | the version becomes `failed` with reason `UPLOAD_EXPIRED` and its staging object `uploads/<asset>/<version>` is deleted (if any); a later completion returns the version unchanged (`failed`, `UPLOAD_EXPIRED`, as completion is idempotent) — the client adds a new version |
| AC2 (edge)        | a version `pending_upload` for less than 24 h, or completed while maintenance runs                | maintenance runs           | it is left alone: the expiry only applies to a version that is still `pending_upload` at the moment it is saved (guarded update), so a racing completion wins or loses cleanly                                                                                               |
| AC3               | an object under `uploads/` older than 24 h whose version is missing or no longer `pending_upload` | maintenance runs           | the object is deleted; objects younger than 24 h and objects outside `uploads/` are never touched                                                                                                                                                                            |
| AC4               | idempotency keys older than the 24 h window                                                       | maintenance runs           | they are deleted; younger keys stay                                                                                                                                                                                                                                          |
| AC5 (concurrency) | several workers (or restarts)                                                                     | they poll                  | maintenance runs at most once per interval (default 1 h, `KILN_MAINTENANCE_INTERVAL_SECONDS`) across all workers, decided by the database clock                                                                                                                              |
| AC6 (limits)      | a large backlog of garbage                                                                        | one run                    | each sweep handles at most 500 items per run (oldest first); the rest is handled by later runs; job processing is not blocked for longer than one run                                                                                                                        |
| AC7 (negative)    | storage or the database fails during maintenance                                                  | maintenance runs           | the error is logged with its type, the worker keeps processing jobs, a failed object deletion is retried by a later run (the sweep finds the object again), and no version is marked expired without being saved first                                                       |
| AC8               | a run finishes                                                                                    | logs are read              | one line per run: expired versions, deleted staging objects, purged keys, duration — no file names or asset names                                                                                                                                                            |
| AC9               | a failed version with reason `UPLOAD_EXPIRED`                                                     | the gallery detail renders | a readable reason in English and Vietnamese ("The upload was never completed. Upload the file again.")                                                                                                                                                                       |

## Non-functional

- Security (A01/A04/A09): deletions only under `uploads/` (prefix fixed in code, keys parsed and checked before deleting); logs without names; no new endpoint.
- Reliability: every step idempotent; the run lease is a single-row upsert on the database clock, so a crashed run is simply retried at the next interval; maintenance errors never stop job processing.
- Performance: partial index on pending versions by `created_at`; bounded batches; `ListObjectsV2` paginated with a prefix and stopped after the batch.

## Out of scope

- Expiring `failed`/abandoned assets themselves, deleting final objects or thumbnails of deleted assets (no delete feature yet), multipart-upload cleanup (uploads are single presigned POSTs), a metrics endpoint.

## References

- AWS S3 — lifecycle rules expiring objects by prefix (the storage-level alternative, not used: it cannot update the version's status, and SeaweedFS support differs): https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html
- AWS S3 `ListObjectsV2` (prefix, pagination, `LastModified`): https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListObjectsV2.html
- IETF draft-ietf-httpapi-idempotency-key-header-08 §2.6 (keys expire after a window): https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/
- PostgreSQL `INSERT … ON CONFLICT DO UPDATE … WHERE` (single-statement lease): https://www.postgresql.org/docs/current/sql-insert.html#SQL-ON-CONFLICT
- `references/data-and-reliability.md` (idempotent consumers, bounded work, retention).

## Design

- Domain: `PENDING_UPLOAD → FAILED` becomes a legal transition; `FailureReason.UPLOAD_EXPIRED`.
- Migration `0004_maintenance`: failure-reason check gains `UPLOAD_EXPIRED`; table `maintenance_runs(task text primary key, last_started_at timestamptz not null)`; partial index `asset_versions(created_at) WHERE status = 'pending_upload'`.
- API package: `SqlMaintenanceStore` (`try_start`, `stale_pending_versions`), `ObjectStorage.list_keys(prefix, older_than, limit)`; `purge_expired_keys` (exists) uses the database clock.
- Worker: `kiln_worker/maintenance.py` `Maintenance.run()` → `MaintenanceReport`; `Worker.run` checks at most once a minute whether a run is due (cheap local gate before the database lease).
- Web: `UPLOAD_EXPIRED` copy; OpenAPI regenerated.

## QA

| AC  | Test(s)                                                                                                                                                                                                                                                                                                                                                  | Result |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| AC1 | `worker/tests/test_maintenance.py` "an upload never completed within 24 hours expires and its staging object goes", "a completion after expiry returns the expired version unchanged"; `test_assets_domain.py` transition table                                                                                                                          | pass   |
| AC2 | `worker/tests/test_maintenance.py` same test (23 h 59 m version kept), "a version completed while maintenance runs is left alone"                                                                                                                                                                                                                        | pass   |
| AC3 | `worker/tests/test_maintenance.py` "old staging objects go only when their version moved on or is gone" (also: young, malformed, outside `uploads/`, clock-skewed waiting object kept); `test_s3_adapter.py` "listing keeps only old keys and stops at the limit"; `test_s3_storage.py` "listing finds old objects under a prefix only" (real SeaweedFS) | pass   |
| AC4 | `worker/tests/test_maintenance.py` "expired idempotency keys are purged"; `test_idempotency_store.py` (window edge, batch oldest first, database clock)                                                                                                                                                                                                  | pass   |
| AC5 | `test_maintenance_store.py` "a run starts once per interval", "concurrent workers get exactly one run" (8 threads, database clock); `worker/tests/test_maintenance.py` "maintenance runs once per interval and asks at most once a minute"                                                                                                               | pass   |
| AC6 | `worker/tests/test_maintenance.py` "each sweep handles one batch per run"; `test_maintenance_store.py` "stale pending versions are found oldest first and bounded"; `test_idempotency_store.py` "purging removes at most a batch oldest first"                                                                                                           | pass   |
| AC7 | `worker/tests/test_maintenance.py` "a storage failure is logged, jobs go on and a later run finishes the cleanup", "a listing failure keeps what was already expired"; `test_s3_adapter.py` "listing errors are reported as unavailable"                                                                                                                 | pass   |
| AC8 | `worker/tests/test_maintenance.py` "one log line per run with counts and no names"                                                                                                                                                                                                                                                                       | pass   |
| AC9 | `AssetDetail.test.tsx` "explains an upload that was never completed"; `locales.test.ts` key parity                                                                                                                                                                                                                                                       | pass   |

Also: `test_migrations.py` "migration 0004 downgrade maps expired uploads to a reason the old check allows" and the schema/migration parity test; `test_main.py` cleans the lease row its loop may take.

Gates: `make ci` green — Python 387 passed (99 %), ui 16, web 89 tests; `make e2e` 12 passed (the worker in e2e runs maintenance against the dev database).

Mutation checks (each reverted after, `PYTHONDONTWRITEBYTECODE=1`): 13 of 13 killed — lease boundary, staleness boundary, oldest-first order (versions and keys), guarded save, staging delete after expiry, malformed-key skip, waiting-version skip, missing-version delete, purge wired in, listing age filter and limit, the once-a-minute local gate.

Exploratory: an order-dependent failure found while testing — the worker entry-point test ran the real loop, which took a maintenance lease on the real clock and left it behind; the test now uses the cleaning `engine` fixture.

## Review score

| #   | Criterion | Score | Evidence |
| --- | --------- | ----- | -------- |
