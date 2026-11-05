# KILN-4: Job queue on Postgres and a worker that makes image thumbnails

- Release: v0.1 · Status: doing · Owner: Claude (deliver-loop)

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

## Design

- Table `jobs(id uuid pk, kind text, version_id uuid fk, payload jsonb, status queued|running|done|dead, attempts int, run_after timestamptz, leased_until timestamptz, last_error text, created_at, updated_at)`; partial index on `(run_after) WHERE status = 'queued'`. `asset_versions.etag text` (migration `0003`).
- API: completion writes the ETag and the job in the unit of work (KILN-21 refactor).
- Worker (`services/worker`): `JobQueue` port with a Postgres adapter (claim with `SKIP LOCKED` and a lease), `ThumbnailProcessor` with `ObjectStorage` (shared adapter from `kiln_api`), a loop with backoff sleeps and graceful shutdown on SIGTERM.
- Failure reasons as an enum stored on the version (`failure_reason`).

### Design as built

- Migration `0003_jobs_and_processing`: `jobs` (one per version and kind, partial indexes on `run_after` for queued and `leased_until` for running jobs), `asset_versions.etag`, `asset_versions.failure_reason` with a check that it is set exactly when the status is `failed`, and `assets.cover_version_id`.
- API: completion heads the final object, then in one unit of work saves `processing` with the ETag and enqueues the job (outbox). `thumbnail_url` is a presigned GET of `thumbs/<asset_id>/<version_id>.webp` for ready image versions and for the asset's cover; `failure_reason` is returned on failed versions.
- `SqlJobQueue` (`kiln_api/repositories/jobs.py`): claim = `UPDATE … WHERE id = (SELECT … FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING`, also reclaiming running jobs whose lease expired; `finish`, `retry`, `bury`, `counts`.
- Worker (`kiln_worker/runner.py`): built on the API's repositories and storage adapter; downloads into a `SpooledTemporaryFile` (16 MB in memory, then disk); a version that moved on meanwhile is skipped without overwriting; models are marked ready without a preview until KILN-5. `python -m kiln_worker` installs SIGTERM/SIGINT handlers and finishes the current job before stopping.
- Not built here (backlog): purging orphaned staging objects and expired keys (KILN-22), a storage circuit breaker (KILN-23), a health endpoint for the worker (logs carry job id, version id, outcome and duration).

## QA

| AC  | Test(s)                                                                                                                                                                                                                                                                                                                                                                                                    | Result |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| AC1 | `api/test_processing_api.py::test_completion_records_the_etag_and_queues_one_thumbnail_job` (repeat completion still one job), `::test_a_failed_completion_queues_nothing`                                                                                                                                                                                                                                 | pass   |
| AC2 | `db/test_job_queue.py` (8: lease and attempt, `run_after`, 4 workers draining 10 jobs with no duplicate, expired lease reclaimed, finish, retry, bury and counts, backoff schedule), `worker/test_runner.py::test_an_empty_queue_does_nothing`, `::test_the_loop_sleeps_when_idle_and_stops_when_asked`                                                                                                    | pass   |
| AC3 | `worker/test_runner.py::test_an_uploaded_image_gets_a_thumbnail_and_becomes_the_cover`, `::test_an_older_version_finishing_late_does_not_take_the_cover`, `worker/test_thumbnail.py` (14: PNG/JPEG/WebP to 512 px WebP, no upscaling, EXIF orientation applied and metadata stripped, alpha kept)                                                                                                          | pass   |
| AC4 | `worker/test_runner.py::test_a_file_changed_after_completion_fails_without_rendering`                                                                                                                                                                                                                                                                                                                      | pass   |
| AC5 | `worker/test_runner.py::test_bad_images_fail_with_a_reason` (unreadable, 400 MP header), `worker/test_thumbnail.py` (header over 50 MP refused before decoding, exactly 50 MP passes the check, corrupt, mislabelled, GIF outside the allow-list, truncated, model bytes)                                                                                                                                  | pass   |
| AC6 | `worker/test_runner.py::test_storage_outages_are_retried_with_backoff_then_given_up` (5/25/125/625 s, then `PROCESSING_GAVE_UP` and a dead job), `db/test_job_queue.py::test_a_running_job_whose_lease_expired_is_claimed_again`, `worker/test_runner.py::test_a_version_changed_while_rendering_closes_the_job_without_overwriting`, `::test_a_job_for_a_version_that_moved_on_is_closed_without_changes` | pass   |
| AC7 | `api/test_processing_api.py::test_versions_and_assets_expose_thumbnails_only_when_ready`, `::test_a_failed_version_shows_its_reason`                                                                                                                                                                                                                                                                       | pass   |
| AC8 | `worker/test_runner.py::test_job_logs_name_the_job_but_not_the_file`, `worker/test_main.py` (starts, logs, stops; SIGTERM stops the loop)                                                                                                                                                                                                                                                                  | pass   |

Also: `worker/test_runner.py::test_a_model_is_marked_ready_without_a_thumbnail_until_kiln_5`; `integration/test_s3_storage.py::test_upload_download_and_a_signed_get_round_trip` and `::test_download_and_upload_report_an_unreachable_storage` against SeaweedFS.

Performance (manual, laptop, worst-case random-noise images 4096 × 4096): PNG 50 MB → 117 ms, JPEG 10 MB → 69 ms, WebP 12 MB → 497 ms; budget 2 s.

Mutation checks (`PYTHONDONTWRITEBYTECODE=1`, code restored each time), all killed: no ETag check, any decoder, no 50 MP check, `<=` on the lease, cover always overwritten, EXIF kept in the thumbnail.

Counts from `pytest --collect-only`: `test_runner.py` 12, `test_thumbnail.py` 14, `test_main.py` 2, `test_job_queue.py` 8, `test_processing_api.py` 4; total suite 330.

Gates: `make ci` green — Python 330 passed, coverage 99 %; ruff and mypy strict clean.

## Review score

_Pending independent review._
