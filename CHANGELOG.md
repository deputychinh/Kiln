# Changelog

Follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [SemVer](https://semver.org/). One version for every part of the repo; one `v0.x` release per week.

## [Unreleased]

### Added

- Processing groundwork (KILN-4, part 1): migration `0003` adds the `jobs` table (one job per version and kind, partial indexes for claiming), the final object's ETag, a database-enforced failure reason on failed versions and the asset cover; the worker's thumbnail processor makes 512 px WebP previews with allow-listed decoders only, a 50-megapixel check before decoding, EXIF orientation applied and metadata stripped.
- Idempotent creation (KILN-21): `POST /api/v1/assets` and `POST /api/v1/assets/{id}/versions` accept an optional `Idempotency-Key` (sf-string per IETF draft-08); a repeat within 24 h replays the first result with `Idempotent-Replayed: true` (re-signing the upload form only while the version is `pending_upload`, otherwise `upload: null` — `upload` is therefore nullable in the contract, though a first creation always has one); a repeated `Idempotency-Key` header → `400`; reuse with another body or endpoint → `422 IDEMPOTENCY_KEY_REUSED`; a duplicate waits for the first request in the same transaction (`409 IDEMPOTENCY_KEY_IN_USE` past the lock timeout); invalid keys → `400`; failed requests do not store the key; migration `0002_idempotency_keys` and a purge function for expired keys.
- Uploads (KILN-3): `POST /api/v1/assets` and `POST /api/v1/assets/{id}/versions` return a presigned POST to a staging key that pins key, type and exact size (ADR 0004); `POST /api/v1/asset-versions/{id}/completions` checks the object and promotes it to an immutable final key with an ETag-conditional copy (ADR 0005), idempotent and resumable; list, detail and version reads; `/ready` checks Postgres and storage and creates the bucket; database lock and statement timeouts; storage timeouts with bounded retries; every error (database, unexpected) as problem details, `503` with `Retry-After`; 1 MB request body limit; documented problem responses in OpenAPI (`application/problem+json`, `Retry-After`, `Location`); concurrent completions are safe against real storage; `/ready` answers within about 1 s even when storage is down.
- Asset and version model (KILN-2): UUID v7 ids, name, file-name, media-type and size rules, the version life cycle, Postgres schema with database-enforced invariants, first Alembic migration, and a repository with keyset pagination, row-locked version numbering and compare-and-set status changes.
- Local S3 storage on SeaweedFS (ADR 0003) because MinIO images are no longer published.
- Repository bootstrap: Prettier, EditorConfig, husky + commitlint, Makefile, CI, docs (conventions, testing, ADR 0001–0002, architecture, security, design system, plan, backlog).
- API skeleton: `/health` and `/ready`, RFC 9457 problem details with stable codes, request ids, OpenAPI export.
- Worker skeleton with typed settings.
- Design system package with tokens (dark default, light theme, reduced motion) and `Button`.
- `kiln` CLI skeleton (`--version`, `--help`).
- Web app skeleton: app shell with skip link, API status through generated OpenAPI types, English and Vietnamese copy, Playwright smoke with axe checks.
