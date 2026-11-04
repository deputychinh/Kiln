# KILN-2: Asset and version model, first migration, repository

- Release: v0.1 · Status: doing · Owner: Claude (deliver-loop)

## Story

As a **studio artist**, I want every file I publish to be stored as a numbered version of a named asset, so that leads can review the history of a piece of work instead of a pile of loose files.

INVEST: Independent ☑ (no UI, no storage yet) · Negotiable ☑ · Valuable ☑ (every later story builds on it) · Estimable ☑ · Small ☑ (one layer: domain + persistence) · Testable ☑

## Acceptance criteria

| Id              | Given                                                                                                 | When                                                                 | Then                                                                                                                                                                     |
| --------------- | ----------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| AC1             | a valid name and an upload description (file name, content type, size)                                | an asset is created                                                  | the asset has a time-ordered UUID v7 id, the trimmed name, a kind derived from the content type, and version 1 in status `pending_upload`                                |
| AC2             | an existing asset                                                                                     | a new version is added                                               | it gets the next number (2, 3, …) and status `pending_upload`; numbers never repeat for one asset, even under two concurrent writers                                     |
| AC3             | a version                                                                                             | its status changes                                                   | only `pending_upload → processing → ready`, `processing → failed` and `failed → processing` (retry) are allowed; any other transition raises `INVALID_STATUS_TRANSITION` |
| AC4 (negative)  | a blank name, a name over 120 characters, or one with control characters                              | an asset is created                                                  | it is rejected with `INVALID_ASSET_NAME`                                                                                                                                 |
| AC5 (negative)  | a content type other than PNG, JPEG, WebP or glTF binary                                              | an asset is created                                                  | it is rejected with `UNSUPPORTED_MEDIA_TYPE`                                                                                                                             |
| AC6 (edge)      | a size of 0 bytes, or above 500 MB (524 288 000 bytes)                                                | an asset is created                                                  | it is rejected with `INVALID_FILE_SIZE`; exactly 1 byte and exactly 500 MB are accepted                                                                                  |
| AC7             | 25 assets                                                                                             | the first page of 10 is read, then the next with the returned cursor | pages are newest first, do not overlap or skip, the last page has no `next_cursor`; a malformed cursor raises `INVALID_CURSOR`; `limit` is clamped to 1–100              |
| AC8             | an unknown id                                                                                         | an asset is fetched                                                  | `ASSET_NOT_FOUND` is raised                                                                                                                                              |
| AC10 (negative) | an asset of one kind (image)                                                                          | a version with a content type of another kind (glTF) is added        | it is rejected with `ASSET_KIND_MISMATCH`                                                                                                                                |
| AC11 (edge)     | a file name with directories (`../../etc/passwd`, `C:\\tex\\rock.png`), blank, or over 255 characters | an asset or version is created                                       | directories are stripped (`passwd`, `rock.png`); blank or too long is rejected with `INVALID_FILE_NAME`                                                                  |
| AC9             | an empty database                                                                                     | `make migrate` runs, then the migration is downgraded                | tables, constraints and indexes are created, and the downgrade removes them cleanly                                                                                      |

## Non-functional

- Security: object keys are generated by the server (`assets/<asset_id>/v<n>/<version_id>.<ext>`) and never contain the user's file name (path traversal, A01/A05); names are stored as given after trimming, rendering escapes them.
- Reliability: the database enforces the invariants too (unique `(asset_id, number)`, status check, size check), so a bug in Python cannot store bad data.
- Performance: list queries use keyset pagination on `(created_at, id)` with an index; no `OFFSET`, no `COUNT(*)`.
- Accessibility / UX: not applicable (no interface in this story).

## Out of scope

- HTTP endpoints, presigned URLs and storage (KILN-3), jobs (KILN-4), users and ownership (KILN-12), deleting assets.

## References

- RFC 9562 §5.7 — UUID version 7 (time-ordered ids): https://www.rfc-editor.org/rfc/rfc9562#section-5.7
- Zalando RESTful API Guidelines — cursor-based pagination: https://opensource.zalando.com/restful-api-guidelines/#160
- Autodesk Flow Production Tracking (ShotGrid) — a _Version_ entity links each review submission to the asset it belongs to; Kiln mirrors that model: https://help.autodesk.com/view/SGSUB/ENU/?guid=SG_Supervisor_Artist_sa_versions_html
- `references/data-and-reliability.md` (constraints in the database, keyset pagination) and `references/backend-architecture.md` (pure domain, ports).

## Design

- **Domain** (`kiln_api/domain/assets.py`, pure, no framework imports — pinned by `tests/unit/test_layering.py`): frozen dataclasses `Asset`, `AssetVersion`, `UploadSpec`; `new_asset()`, `new_version()`, `transition()`; names and file names reject Unicode categories Cc, Cf, Zl, Zp (control, bidi/zero-width, separators) and `.`/`..`; timestamps must carry a timezone. `AssetKind`, `VersionStatus` in `enums.py`; limits in `constants.py`; errors in `errors.py` (framework-free); the HTTP mapping lives in `problems.py`.
- **Ids**: `domain/ids.py` generates UUID v7 (Python 3.12 has no `uuid.uuid7`).
- **Object keys**: `assets/<asset_id>/v<n>/<version_id>.<ext>`, the extension derived from the media type, never from the user's file name.
- **Ports** (`ports.py`): `AssetRepository` (`add`, `get`, `list_page`, `add_next_version`, `get_version`, `versions_of`, `save_version(version, expected=…)`), `Clock`; `Page[T]`.
- **Persistence**: SQLAlchemy 2 Core tables in `db/schema.py`; `repositories/assets.py` (`SqlAssetRepository`). `add_next_version` takes `SELECT … FOR UPDATE` on the asset row so concurrent writers serialise; `save_version` is a compare-and-set on the expected status, so a stale writer gets `INVALID_STATUS_TRANSITION` instead of overwriting. Alembic lives in `services/api/migrations/` (revision `0001_assets`, names marked final with `op.f`).
- **Cursor**: opaque URL-safe base64 of `created_at|id`, at most 128 characters; anything else → `INVALID_CURSOR`.
- **Status codes**: an unsupported media type declared in the JSON body is `422 UNSUPPORTED_MEDIA_TYPE` (415 is reserved for the request's own format).
- **Tests**: unit tests for the domain; repository and migration tests against Postgres (`KILN_TEST_DATABASE_URL`, compose locally, a service container in CI). The test database name must end in `_test`; if Postgres is unreachable the session fails with "run make up" rather than skipping.

## QA

| AC   | Test(s)                                                                                                                                                                                                                                                                                                                                                          | Result |
| ---- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| AC1  | `unit/test_assets_domain.py::test_a_new_asset_starts_with_version_one_pending_upload`, `::test_a_glb_upload_makes_a_model_asset`, `unit/test_ids.py` (3)                                                                                                                                                                                                         | pass   |
| AC2  | `db/test_asset_repository.py::test_new_versions_take_the_next_number`, `::test_concurrent_writers_never_get_the_same_version_number` (4 threads), `::test_the_database_rejects_a_duplicate_version_number`                                                                                                                                                       | pass   |
| AC3  | `unit/test_assets_domain.py::test_allowed_status_paths` (3 paths), `::test_forbidden_status_transitions_raise` (7), `db/…::test_a_saved_status_change_is_persisted`                                                                                                                                                                                              | pass   |
| AC4  | `::test_invalid_asset_names_are_rejected` (6), `::test_a_name_of_exactly_120_characters_is_accepted`                                                                                                                                                                                                                                                             | pass   |
| AC5  | `::test_unsupported_media_types_are_rejected` (4), `::test_media_types_are_matched_case_insensitively_with_parameters_ignored`                                                                                                                                                                                                                                   | pass   |
| AC6  | `::test_sizes_outside_one_byte_to_500_mb_are_rejected` (0, −1, max+1), `::test_the_size_boundaries_are_accepted` (1, max)                                                                                                                                                                                                                                        | pass   |
| AC7  | `db/…::test_pages_are_newest_first_without_gaps_or_overlap` (25 / 10), `::test_assets_created_in_the_same_instant_are_still_paged_exactly_once`, `::test_an_exactly_full_last_page_has_no_next_cursor`, `::test_an_empty_database_gives_an_empty_page`, `::test_the_page_limit_is_clamped` (0, −5, 500), `unit/test_cursor.py` (9, incl. a 129-character cursor) | pass   |
| AC8  | `db/…::test_reading_an_unknown_asset_raises_not_found`, `::test_reading_an_unknown_version_raises_not_found`, `::test_adding_a_version_to_an_unknown_asset_raises_not_found`, `::test_saving_an_unknown_version_raises_not_found`                                                                                                                                | pass   |
| AC9  | `db/test_migrations.py` (schema matches models, downgrade → upgrade, constraint names); `make migrate` on the dev database                                                                                                                                                                                                                                       | pass   |
| AC10 | `::test_a_version_of_another_kind_is_rejected`                                                                                                                                                                                                                                                                                                                   | pass   |
| AC11 | `::test_directories_are_stripped_from_file_names` (3), `::test_blank_long_or_control_character_file_names_are_rejected` (5)                                                                                                                                                                                                                                      | pass   |

Exploratory checks (ISTQB): boundary values on name length (0/1/120/121), size (0/1/max/max+1) and page limit (−5/0/100/500); equivalence classes of media types (supported, unsupported, parameterised, upper case); the version state-transition table (5 allowed + 11 forbidden = all 16 pairs, asserted by a test); error guessing: path traversal in file names, tampered and timezone-less cursors, concurrent writers, identical timestamps in pagination.

Defect found in QA and fixed: the first migration doubled constraint names (`ck_asset_versions_ck_asset_versions_status`) because the naming convention was applied on top of full names; names are now marked final with `op.f()` and a test pins them.

Gates: `make ci` green — Python 108 passed, coverage 99 %; ruff (now with DTZ rules) and mypy strict clean; Node workspaces unchanged and green.

## Review score

_Pending independent review._
