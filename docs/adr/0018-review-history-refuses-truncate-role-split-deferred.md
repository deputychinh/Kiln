# ADR 0018: The review history refuses TRUNCATE; the non-owner runtime role is deferred with its risk accepted

- Status: accepted · 2026-11-08 · Supersedes the TRUNCATE consequence of ADR 0015 ("Truncating `review_events` is still possible for the database owner (tests clean up that way)")

## Context

ADR 0015 and 0016 made `review_events` append-only with a row trigger: no `UPDATE`, and a `DELETE` only from the cascade of a deleted version. `TRUNCATE` fires no row triggers, so one statement could still empty the history, and the test suite cleaned up that way. The app connects as the role that owns the tables (`kiln`, which `docker compose` also makes a superuser), so a statement sent through the app's login — a bug, a mistaken maintenance script, an injection — could also `ALTER TABLE … DISABLE TRIGGER` or drop the table. The KILN-11 review filed this as KILN-51 with two remedies: a `BEFORE TRUNCATE` guard, and a runtime role that is not the owner.

## Decision

1. **A statement-level `BEFORE TRUNCATE` trigger** on `review_events` (`review_events_no_truncate`, migration 0013, the same in `db/schema.py`) runs the existing `review_events_append_only()` function, which raises `review_events is append-only` (`restrict_violation`) for anything but the cascade delete. It also fires for `TRUNCATE assets CASCADE`, which reaches `review_events` through the foreign keys. The function body is unchanged; the migration only adds a trigger (a brief `SHARE ROW EXCLUSIVE` lock under the migration `lock_timeout`, no rewrite).
2. **Tests clean up through the cascade**: the fixture deletes rows table by table and leaves `review_events` to the cascade from `asset_versions`, so the suite needs neither `TRUNCATE` nor a disabled trigger.
3. **The non-owner runtime role is not part of this change.** Splitting the login (migrations as the owner; the API, worker and CLI as a role with only `SELECT, INSERT, UPDATE, DELETE` and sequence use) touches the compose init, `.env.example` and settings (a second URL for Alembic), default privileges for every future migration, the CI service container, the test fixtures (two roles per test database) and the e2e servers, and needs a one-time step on every existing database. It is filed as **KILN-58**.

## Consequences

- Accepted risk until KILN-58: whoever can run SQL as the app's login (the owner, and a superuser in the local and CI setups) can still `DISABLE TRIGGER`, `DROP TRIGGER` or drop the table. The triggers stop mistakes and the app's own statements, not a hostile owner. Grants never stop a superuser, so KILN-58 also means a deployment must not run the app as one.
- `TRUNCATE review_events` now fails everywhere, tests and maintenance included; deleting a version or an asset still removes its history.
- `test_constraint_and_index_definitions_match_the_schema_module` compares the new trigger (`pg_get_triggerdef`) and the function (`pg_get_functiondef`) between the migrated database and one built from the module.

## Sources

PostgreSQL 17 docs: CREATE TRIGGER (`TRUNCATE` triggers are statement-level only), TRUNCATE (`CASCADE` fires the truncated tables' triggers), ALTER TABLE (`DISABLE TRIGGER` needs ownership), Privileges; ADR 0015, ADR 0016; OWASP Top 10:2025 A09 (logging and alerting failures: tamper-proof audit trails).
