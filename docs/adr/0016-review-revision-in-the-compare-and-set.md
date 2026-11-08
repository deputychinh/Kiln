# ADR 0016: The reviewer's revision in the compare-and-set; a cascade-only delete of review events

- Status: accepted · 2026-11-08 · Supersedes ADR 0015 §3, and the trigger rule in §4

## Context

ADR 0015 §3 said the review compare-and-set refuses "a decision made on a state that changed between read and write (including approve → reopen → approve, which a state-only check would miss)". That held only between the API's own read and its write, inside one request. The client sent only `expected_state`, so a reviewer whose page still showed revision 0 could approve a version that someone else had meanwhile approved and reopened (back to `in_review` at revision 2): the KILN-11 review got 201 for that stale decision. Separately, §4's trigger let a delete through whenever it ran inside any trigger (`pg_trigger_depth() > 1`), not only inside the cascade from a deleted version.

## Decision

1. **The client names the revision it saw.** `POST …/review-transitions` takes an optional `expected_revision` (the version's `review_revision`, an integer ≥ 0). When it is sent, the domain refuses any other revision with `409 REVIEW_STATE_CONFLICT`, even when the state is the same. The problem details carry `current_state` and `current_revision`, so the client can show the state and resend with the revision it now knows. The web app always sends it. It stays optional so the CLI and scripts can decide on the state alone, which is the ADR 0015 behaviour. The write keeps its guard on the state and revision the API read (and `ready` for a decision).
2. **A delete of an event needs the cascade.** The trigger function allows a delete only when it is nested (`pg_trigger_depth() > 1`) **and** the event's version no longer exists. Migration 0012 replaces the function body in place, and the schema module creates the same body. A test compares `pg_get_functiondef` of the migrated database with one built from the module.

## Consequences

- Approve → reopen → approve is refused for any client that sends its revision; one that sends only the state accepts that risk.
- A trigger added later cannot erase history by accident; deleting a version still removes its events.
- The web app's idempotency key now covers the version, the revision, the action and the note, so a retry replays only the same decision on the same revision.

## Sources

ADR 0015; RFC 9110 §13.1.1 (`If-Match`): the same idea as a body field, kept beside `expected_state`; RFC 9457 §3.2 (extension members); PostgreSQL 17 docs, `pg_trigger_depth()` and referential actions run as triggers.
