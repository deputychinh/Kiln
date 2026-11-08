# ADR 0025: A function's pinned search_path names only trusted schemas, pg_catalog first and pg_temp last

- Status: accepted · 2026-11-08 · Supersedes ADR 0023 Decision 3's rule "Every function in the schema must pin its `search_path` with `pg_temp` last"; ADR 0023 stays unedited

## Context

ADR 0023 required every function in the `public` schema to pin a `search_path` ending in `pg_temp`, and a generic test enforced it by checking only that the setting ended with `, pg_temp`. The KILN-39/51 final review showed that the test accepted `public, pg_catalog, pg_temp`: a schema searched before `pg_catalog` can define a function or operator named like a built-in (`lower`, `=`) and capture the call (CVE-2018-1058). It also accepted `pg_temp` named twice (first and last), a quoted `"$user"` or any other schema someone else might create or fill.

## Decision

A function's pin is safe only when all of these hold (KILN-61):

1. it sets `search_path`;
2. it names only `pg_catalog`, `public` and `pg_temp`, each at most once;
3. `pg_temp` is last;
4. `pg_catalog` is first when it is named. Leaving it out is allowed: PostgreSQL then searches it first anyway.

The test reads `pg_proc.proconfig` as an array, splits the value at commas, and reports each faulty function with its reason. A parametrized test sets each unsafe and safe pin on a real probe function in a rolled-back transaction, so the check is proven against what PostgreSQL stores.

## Consequences

- Today's only function (`review_events_append_only`, `pg_catalog, public, pg_temp`) passes unchanged; no migration.
- A new schema (for example a future `audit`) must be added to the trusted set in the test, on purpose, with a reason.

## Sources

PostgreSQL 17 docs: CREATE FUNCTION ("Writing SECURITY DEFINER Functions Safely"), `search_path` (`pg_catalog` searched first when not named; the temporary schema searched first for relations when not named), `pg_proc.proconfig`; CVE-2018-1058; ADR 0023.
