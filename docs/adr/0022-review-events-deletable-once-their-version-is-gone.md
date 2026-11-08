# ADR 0022: A review event may be deleted once its version is gone, nested in a cascade or not

- Status: accepted · 2026-11-08 · Supersedes ADR 0016 §2 (a delete needs the cascade: nested and the version gone) and ADR 0020 §3 (orphans kept)

## Context

ADR 0016 let the append-only function pass a `DELETE` only when it is nested (`pg_trigger_depth() > 1`) **and** the event's version no longer exists: the foreign key's cascade from deleting a version. ADR 0020 made the triggers fire in replica mode, where that cascade does not fire, and accepted that deleting a version there leaves its events behind. The KILN-51 gate review (round 2) showed what that means: such an orphan can never be deleted, since a direct `DELETE` is not nested. It also blocks deleting the user who acted in it, because `review_events.actor_id` references `users`.

## Decision

1. Migration 0015 replaces the function body (no table touched): a `DELETE` passes when the event's version no longer exists, nested or not. While the version exists, every delete is refused, whoever sends it, so the history of a live version stays append-only. `UPDATE` and `TRUNCATE` are refused as before. `db/schema.py` has the same body, and the parity test compares them.
2. Cleanup after a replica-mode delete is an ordinary statement any role with `DELETE` on the table can run: `DELETE FROM review_events e WHERE NOT EXISTS (SELECT 1 FROM asset_versions v WHERE v.id = e.version_id)`. `docs/security.md` records it; no owner or superuser step is needed.

## Consequences

- The nesting condition guarded nothing extra. A trigger that deletes events while their version exists is still refused (`test_a_delete_from_another_trigger_is_refused_while_the_version_exists`), and once the version is gone the events have nothing left to describe.
- `test_an_event_orphaned_in_replica_mode_can_be_cleaned_up_afterwards` proves the orphan appears and can then be removed; `test_migration_0015_drops_the_nesting_condition_and_downgrades` checks the body before and after.

## Sources

PostgreSQL 17 docs: `session_replication_role` (referential actions are implemented as triggers that do not fire in replica mode), CREATE FUNCTION; ADRs 0016 and 0020.
