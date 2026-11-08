# ADR 0023: The append-only check reads `public.asset_versions` with a pinned search_path

- Status: accepted · 2026-11-08 · Supersedes ADR 0022's Decision 1 sentence "While the version exists, every delete is refused, whoever sends it" and its first Consequence ("The nesting condition guarded nothing extra")

## Context

ADR 0022 (migration 0015) dropped the nesting condition from `review_events_append_only()`. A `DELETE` of an event then passed whenever `NOT EXISTS (SELECT 1 FROM asset_versions WHERE id = OLD.version_id)`. The reason was sound: replica mode skips the foreign key's cascade, so deleting a version there left events that could never be deleted and that blocked deleting their actor. But it made that one existence check the whole guard. The check named `asset_versions` without a schema, and the function set no `search_path`. The KILN-51 gate review (round 3) showed a role with only DML rights running `CREATE TEMP TABLE asset_versions (id uuid); DELETE FROM review_events …`. The temporary table answered "gone" for a live version and the history was erased. This was reproduced on this repo's PostgreSQL 17 as a non-owner, non-superuser role. ADR 0022's claims that every delete of a live version's event is refused, and that the nesting condition guarded nothing extra, were therefore wrong: nesting was what stopped a direct statement from reaching the check at all.

## Decision

1. Migration 0016 replaces the function in place (no table touched). The check reads **`public.asset_versions`**, and the function carries **`SET search_path = pg_catalog, public, pg_temp`**. `pg_temp` is named last on purpose: PostgreSQL searches the session's temporary schema **first** for tables when `search_path` does not name it, so `pg_catalog, public` alone would not have closed the hole. With qualified names and a pinned path, no session setting or temporary object changes what the function reads.
2. The nesting condition stays dropped: replica-mode orphans still need a direct delete (ADR 0022 §2). With the check now trustworthy, a direct delete passes only when the version really is gone, which a DML role can bring about only by deleting the version, and that removes the history through the cascade anyway.
3. Every function in the schema must pin its `search_path` with `pg_temp` last. Today that is only this one, which also serves the `TRUNCATE` trigger. A generic test lists `pg_proc` for the `public` schema and fails on any function that does not. The schema-parity test now compares each function's `proconfig` as well as its definition, and `db/schema.py` creates the same pinned, qualified function.

## Consequences

- Accepted, as before: deleting a version removes its history by design, and a session that then re-inserts a row with the same version id shows that version with no history. The API never re-inserts an id; only a direct SQL session can, which is the owner's until KILN-58 splits the roles.
- A future trigger or `SECURITY DEFINER` function that forgets the pin fails CI.

## Sources

PostgreSQL 17 docs: CREATE FUNCTION ("Writing SECURITY DEFINER Functions Safely": `pg_temp` is searched first unless listed, so list it last), the `search_path` configuration (the temporary schema is searched first by default for relations), `pg_proc.proconfig`; CVE-2018-1058 (search_path abuse); ADRs 0016 and 0022.
