# KILN-4: Job queue on Postgres and a worker that makes image thumbnails

- Release: v0.1 · Status: todo (BA done) · Owner: Claude (deliver-loop)

## Story

As a **lead reviewing work in the gallery**, I want every uploaded image to get a small preview within seconds, so that I can scan a hundred textures without downloading each file.

INVEST: Independent ☑ (needs KILN-3 completion only) · Negotiable ☑ · Valuable ☑ · Estimable ☑ · Small ☑ (images only; `.glb` thumbnails are KILN-5) · Testable ☑

## Acceptance criteria

| Id                | Given                                                                                                                          | When                                                           | Then                                                                                                                                                                                                                                                                           |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| AC1               | an upload completion                                                                                                           | the version moves to `processing`                              | a `thumbnail` job is written **in the same transaction**, recording the final object's ETag; no version can be `processing` without a job                                                                                                                                      |
| AC2               | a pending job and a running worker                                                                                             | the worker polls                                               | it claims the job with `FOR UPDATE SKIP LOCKED`, two workers never process the same job, and an idle worker sleeps between polls without busy-looping                                                                                                                          |
| AC3               | an image job                                                                                                                   | it runs                                                        | the worker checks the final object's ETag equals the recorded one, decodes only PNG/JPEG/WebP, writes a WebP thumbnail (longest side 512 px, aspect kept, EXIF orientation applied, metadata stripped) to `thumbs/<asset_id>/<version_id>.webp`, and marks the version `ready` |
| AC4 (negative)    | the final object changed after completion (ETag differs)                                                                       | the job runs                                                   | the version becomes `failed` with reason `UPLOAD_CHANGED`; nothing is rendered                                                                                                                                                                                                 |
| AC5 (negative)    | a corrupt image, a file whose bytes are not the declared type, or a decompression bomb (more than 50 megapixels in the header) | the job runs                                                   | the version becomes `failed` with reason `UNREADABLE_IMAGE` or `IMAGE_TOO_LARGE`, without decoding the pixels of an oversized image                                                                                                                                            |
| AC6 (reliability) | a transient failure (storage down)                                                                                             | the job runs                                                   | it is retried with exponential backoff (5 s, 25 s, 125 s …) up to 5 attempts, then the version becomes `failed` with reason `PROCESSING_GAVE_UP`; a worker crash mid-job releases the job after its lease (5 min) expires                                                      |
| AC7               | a `GET /api/v1/assets/{id}` or the list                                                                                        | a version is `ready`                                           | its JSON has `thumbnail_url` (a presigned GET, 15 min) for each ready version; `null` otherwise                                                                                                                                                                                |
| AC8               | jobs in any state                                                                                                              | `GET /ready` on the worker's health port or `make worker` logs | the worker logs each job start/finish/failure with `job_id`, `version_id`, duration, without file names or content                                                                                                                                                             |

## Non-functional

- Security (A04/A06/A08/A10): only allow-listed decoders (`Image.open(..., formats=[...])`) so GD/PCF loaders with known bomb bypasses (CVE-2026-55380, CVE-2026-54059) are never reached; Pillow ≥ 12.3.0; header dimensions checked before `load()`; `DecompressionBombWarning` treated as an error; source bytes capped by the 500 MB upload limit; thumbnails never contain EXIF/GPS.
- Reliability: at-least-once delivery, idempotent processing keyed by `job_id` (re-running overwrites the same thumbnail key); lease + backoff; dead jobs visible.
- Performance: a 4096 × 4096 PNG thumbnails in under 2 s on a laptop; `Image.draft()` for JPEG; the worker streams the object, not more than one image in memory per worker.
- Observability: queue depth and failed count exposed by a `jobs` summary query (used later by the UI).

## Out of scope

- `.glb` thumbnails (KILN-5), purging orphaned staging objects and expired idempotency keys (KILN-22), a storage circuit breaker (KILN-23), AI tagging (KILN-13).

## References

- PostgreSQL docs, `SELECT … FOR UPDATE SKIP LOCKED` for queue-like tables: https://www.postgresql.org/docs/current/sql-select.html#SQL-FOR-UPDATE-SHARE
- Pillow decompression-bomb guard and 2026 bypass advisories: https://advisories.gitlab.com/pypi/pillow/CVE-2026-55379/, https://securelayer7.net/lab/cve-2026-55380-pillow-gdimagefile-decompression-bomb-dos, https://vulert.com/vuln-db/pillow-pcffontfile-load-bitmaps-image-frombytes-called-without-decompression-bomb-check-
- Real-world failure mode (bomb error surfacing as a 500): https://github.com/rr-/szurubooru/issues/503
- `references/data-and-reliability.md` (outbox, idempotent consumers, retry with backoff, DLQ), ADR 0001 §5 (queue on Postgres), ADR 0005 (ETag recorded at completion).

## Design (draft)

- Table `jobs(id uuid pk, kind text, version_id uuid fk, payload jsonb, status queued|running|done|dead, attempts int, run_after timestamptz, leased_until timestamptz, last_error text, created_at, updated_at)`; partial index on `(run_after) WHERE status = 'queued'`. `asset_versions.etag text` (migration `0003`).
- API: completion writes the ETag and the job in the unit of work (KILN-21 refactor).
- Worker (`services/worker`): `JobQueue` port with a Postgres adapter (claim with `SKIP LOCKED` and a lease), `ThumbnailProcessor` with `ObjectStorage` (shared adapter from `kiln_api`), a loop with backoff sleeps and graceful shutdown on SIGTERM.
- Failure reasons as an enum stored on the version (`failure_reason`).
