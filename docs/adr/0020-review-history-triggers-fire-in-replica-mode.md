# ADR 0020: The review history's triggers fire in replica mode too

- Status: accepted · 2026-11-08 · Supersedes the accepted-risk paragraph of ADR 0018 (Consequences, first point)

## Context

ADR 0018 added a `BEFORE TRUNCATE` trigger to `review_events` and accepted that the app's login, which owns the table, could still disable the triggers. The KILN-51 review found a cheaper bypass it did not name: `SET session_replication_role = replica` makes PostgreSQL skip every trigger enabled in the default (`ORIGIN`) mode, so `SET session_replication_role = replica; TRUNCATE review_events;` succeeded, and the same held for `UPDATE` and `DELETE`. One `SET` is a single statement that a script, a restore tool or a superuser session can run without changing the schema. ADR 0018 is accepted, so it is not edited.

## Decision

1. Migration 0014 runs `ALTER TABLE review_events ENABLE ALWAYS TRIGGER` for `review_events_append_only` and `review_events_no_truncate`; triggers enabled `ALWAYS` fire whatever `session_replication_role` says. It changes the catalogue only: a brief `SHARE ROW EXCLUSIVE` lock under the migration `lock_timeout`, no rewrite. The downgrade puts both back to the default.
2. `db/schema.py` runs the same two statements after creating the triggers, and the schema-parity test now compares each trigger's enabled state (`pg_trigger.tgenabled`) as well as its definition.
3. The foreign-key cascade is left alone. Under `replica` its internal triggers do not fire, so deleting a version there leaves its events behind instead of removing them; history is kept, not lost.

## Consequences

- Accepted risk until KILN-58 (replacing ADR 0018's paragraph): whoever logs in as the table's owner, or as a superuser as in the local and CI setups, can still `ALTER TABLE … DISABLE TRIGGER`, set the triggers back to `ENABLE` and then use replica mode, or drop the table. Both steps are DDL that a review of the database's statements would show, unlike a single `SET`. Replica mode on its own no longer turns the guards off.
- `test_replica_mode_does_not_turn_the_history_guards_off` proves `UPDATE`, `DELETE` and `TRUNCATE` are refused under `replica`; `test_migration_0014_makes_the_history_triggers_fire_always_and_downgrades` checks `tgenabled` going from `O` to `A` and back, with the table's file unchanged.

## Sources

PostgreSQL 17 docs: ALTER TABLE (`ENABLE ALWAYS TRIGGER`, `session_replication_role`), `pg_trigger.tgenabled`, runtime configuration `session_replication_role`; ADR 0018.
