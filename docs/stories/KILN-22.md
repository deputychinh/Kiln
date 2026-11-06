# KILN-22: Scheduled maintenance in the worker

- Release: v0.1 · Status: done · Owner: Claude (deliver-loop)

## Story

As the **person running a Kiln studio server**, I want abandoned uploads and expired idempotency keys cleaned up automatically, so that storage and the database do not grow with garbage and the gallery does not show versions "waiting for upload" forever.

INVEST: Independent ☑ (KILN-3/21/4 data only) · Negotiable ☑ · Valuable ☑ · Estimable ☑ · Small ☑ (three bounded sweeps, no UI beyond one failure reason) · Testable ☑

## Acceptance criteria

| Id                | Given                                                                                             | When                       | Then                                                                                                                                                                                                                                                                                                                                                                                                                            |
| ----------------- | ------------------------------------------------------------------------------------------------- | -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1               | a version still `pending_upload` 24 h after it was created                                        | maintenance runs           | the version becomes `failed` with reason `UPLOAD_EXPIRED` and its staging object `uploads/<asset>/<version>` is deleted (if any); a later completion returns the version unchanged (`failed`, `UPLOAD_EXPIRED`, as completion is idempotent) — the client adds a new version                                                                                                                                                    |
| AC2 (edge)        | a version `pending_upload` for less than 24 h, or completed while maintenance runs                | maintenance runs           | it is left alone: the expiry only applies to a version that is still `pending_upload` at the moment it is saved (guarded update). If the expiry wins against a completion, whichever side finishes last removes the promoted final object (the expiry when the copy landed first, the completion when the copy lands after the expiry), and the completion returns the expired version — nothing is left behind in either order |
| AC3               | an object under `uploads/` older than 24 h whose version is missing or no longer `pending_upload` | maintenance runs           | the object is deleted; objects younger than 24 h and objects outside `uploads/` are never touched                                                                                                                                                                                                                                                                                                                               |
| AC4               | idempotency keys older than the 24 h window                                                       | maintenance runs           | they are deleted; younger keys stay                                                                                                                                                                                                                                                                                                                                                                                             |
| AC5 (concurrency) | several workers (or restarts)                                                                     | they poll                  | maintenance runs at most once per interval (default 1 h, `KILN_MAINTENANCE_INTERVAL_SECONDS`) across all workers, decided by the database clock                                                                                                                                                                                                                                                                                 |
| AC6 (limits)      | a large backlog of garbage                                                                        | one run                    | expiry handles at most 500 versions per run (oldest first) and the staging sweep at most 500 deletions per run; keys that must stay (still waiting, or not written by Kiln) do not count toward that batch, and the listing reads at most 5,000 old keys per run (key order, as S3 lists); the rest is handled by later runs                                                                                                    |
| AC7 (negative)    | storage or the database fails during maintenance                                                  | maintenance runs           | a storage outage stops the storage work of that run (logged with its cause) while the key purge still runs; a database failure is logged and the run ends; either way the worker keeps processing jobs, a failed object deletion is retried by a later run (the sweep finds the object again), and no version is marked expired without being saved first                                                                       |
| AC8               | a run finishes                                                                                    | logs are read              | one line per run: expired versions, deleted staging objects, purged keys, duration — no file names or asset names                                                                                                                                                                                                                                                                                                               |
| AC9               | a failed version with reason `UPLOAD_EXPIRED`                                                     | the gallery detail renders | a readable reason in English and Vietnamese ("The upload was never completed. Upload the file again.")                                                                                                                                                                                                                                                                                                                          |

## Non-functional

- Security (A01/A04/A09): staging deletions only for keys of the form `uploads/<uuid>/<uuid>` (prefix fixed in code, keys parsed and checked before deleting); a final object is deleted only for a version just saved as expired; logs without names; no new endpoint.
- Reliability: every step idempotent (the lease records the start of a run, so with an interval shorter than a run two runs may overlap — harmless); the run lease is a single-row upsert on the database clock, so a crashed run is simply retried at the next interval; maintenance errors never stop job processing.
- Performance: partial index on pending versions by `created_at`; bounded batches; versions looked up 100 ids per query (no N+1); `ListObjectsV2` read lazily page by page and cut after 5,000 keys.

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

| AC  | Test(s)                                                                                                                                                                                                                                                                                                                                                                               | Result |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| AC1 | `worker/tests/test_maintenance.py` "an upload never completed within 24 hours expires and its staging object goes", "a completion after expiry returns the expired version unchanged"; `test_assets_domain.py` transition table                                                                                                                                                       | pass   |
| AC2 | round 3: "completion and expiry racing leave an expired version and no objects" (during the copy / after the copy); `worker/tests/test_maintenance.py` same test (23 h 59 m version kept), "a version completed while maintenance runs is left alone", "expiry after a racing promotion also removes the final object", "a version gone before expiry is skipped"                     | pass   |
| AC3 | `worker/tests/test_maintenance.py` "old staging objects go only when their version moved on or is gone" (young, malformed, outside `uploads/` and clock-skewed waiting objects kept); `test_s3_adapter.py` "listing yields only old keys page by page"; `test_s3_storage.py` "listing finds old objects under a prefix only" (real SeaweedFS)                                         | pass   |
| AC4 | round 3: "expired keys are purged batch after batch up to a bound"; `worker/tests/test_maintenance.py` "expired idempotency keys are purged"; `test_idempotency_store.py` (window edge, batch oldest first, database clock)                                                                                                                                                           | pass   |
| AC5 | `test_maintenance_store.py` "a run starts once per interval", "concurrent workers get exactly one run"; `worker/tests/test_maintenance.py` "maintenance runs once per interval and asks at most once a minute", "the maintenance interval must be positive"                                                                                                                           | pass   |
| AC6 | `worker/tests/test_maintenance.py` "each sweep handles one batch per run", "keys that must stay do not use up the batch", "the staging sweep stops after one batch of deletions", "the staging scan is bounded and looks versions up in chunks"; `test_maintenance_store.py` "stale pending versions are found oldest first and bounded", "versions are looked up by id in one query" | pass   |
| AC7 | `worker/tests/test_maintenance.py` "a storage outage stops the storage work, jobs go on and a later run finishes", "a listing failure keeps what was already expired", "a database failure is logged and jobs go on"; `test_s3_adapter.py` "listing errors are reported as unavailable"                                                                                               | pass   |
| AC8 | `worker/tests/test_maintenance.py` "one log line per run with counts and no names"                                                                                                                                                                                                                                                                                                    | pass   |
| AC9 | `AssetDetail.test.tsx` "explains an upload that was never completed"; `locales.test.ts` key parity                                                                                                                                                                                                                                                                                    | pass   |

Also: `test_migrations.py` "migration 0004 downgrade maps expired uploads to a reason the old check allows" and the schema/migration parity test; `test_main.py` cleans the lease row its loop may take.

Gates (round 3, final): `make ci` green — Python 398 passed (99 %), ui 16, web 89 tests; `make e2e` 12 passed (the worker in e2e runs maintenance against the dev database).

Mutation checks (each reverted after, `PYTHONDONTWRITEBYTECODE=1`): round 1 13/13 killed; round 2 8/9 killed — the survivor was an empty-list guard that only skipped a query returning the same result, so the guard was removed; round 3 5/5 killed.

Exploratory: an order-dependent failure found while testing — the worker entry-point test ran the real loop, which took a maintenance lease on the real clock and left it behind; the test now uses the cleaning `engine` fixture.

## Review rounds

- Round 1 (independent reviewer): 8.0/10 — an expiry winning against a completion that had already promoted the file left the final object in storage for good (reproduced); the staging sweep counted skipped keys toward its batch and could stall behind ≥ 500 of them, and was not "oldest first" as AC6 claimed; N+1 version lookups; one failing item aborted the whole run; the interval was not validated; lease overlap undocumented. All fixed in round 2 (AC2 and AC6 reworded to what the code does).

- Round 2 (fresh reviewer, final gate): **9.0/10, pass** (reliability 0.5, docs 0.5). F1 — a copy landing after the expiry left the final object behind (reproduced with a mid-copy probe) — fixed after the gate: the completion that loses to an expiry deletes the promoted file, and a completion that finds the final object already removed returns the expired version instead of `UPLOAD_NOT_FOUND`; both orders tested. F2 — key purge capped at 500 per run — now up to 10 batches (5,000) per run. Docs: the threat model and the non-functional now say final objects of expired versions are deleted. Accepted and documented: F3 (the 5,000-key scan cap counts only old keys, so ≥ 5,000 foreign keys sorting first under `uploads/` would stall the sweep — nothing but Kiln writes there), F5 (maintenance runs inline in the job loop; a full run pauses job processing for its duration). Post-gate fixes are self-verified by tests and mutants, not re-scored.

## Review score

| #   | Criterion        | Score    | Evidence (reviewer, round 2)                                                          |
| --- | ---------------- | -------- | ------------------------------------------------------------------------------------- |
| 1   | Requirements fit | 1        | AC1–AC9 traced to passing tests                                                       |
| 2   | Test depth       | 1        | unit, DB (8-thread lease), real SeaweedFS listing, e2e; 6/6 reviewer mutations killed |
| 3   | Reliability      | 0.5      | F1 late-copy leak — fixed after the gate                                              |
| 4   | Security         | 1        | only `uploads/<uuid>/<uuid>` keys swept; counts-only logs; no new endpoint            |
| 5   | Maintainability  | 1        | lint 0, ports (`MaintenanceStore`, `iter_keys`), small units                          |
| 6   | UX / API         | 1        | `UPLOAD_EXPIRED` copy in en/vi with a test                                            |
| 7   | Accessibility    | 1        | text only                                                                             |
| 8   | Performance      | 1        | partial index, lookups by 100, lazy listing, bounded batches                          |
| 9   | Docs             | 0.5      | threat model said "only under `uploads/`" — corrected after the gate                  |
| 10  | Delivery         | 1        | gates green, 7 small commits, pushed                                                  |
|     | **Total**        | **9/10** | reviewer: fresh subagent, round 2 (round 1: 8.0)                                      |
