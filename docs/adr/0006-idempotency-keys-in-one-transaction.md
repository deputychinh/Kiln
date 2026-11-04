# ADR 0006: Idempotency keys in the same transaction as the work

- Status: accepted · 2026-11-04

## Context

KILN-21 adds `Idempotency-Key` to the two creation endpoints. The IETF draft (draft-ietf-httpapi-idempotency-key-header-08) recommends `409` for a duplicate that arrives while the first request is still in progress. The common alternative design stores the key in its own transaction ("claim, then work, then complete"), which leaves a window where a crash stores the key without the work, or the work without the key.

## Decision

1. The key row, the created asset or version, and the key's result are written in **one database transaction** through a unit of work (`SqlUnitOfWork`). A failure anywhere rolls all of them back, so a client can retry the same key.
2. A duplicate that arrives during the first request **waits** on the uncommitted key row (Postgres unique-index wait) and then receives the replay. Only a wait longer than `lock_timeout` (5 s, SQLSTATE 55P03) returns `409 IDEMPOTENCY_KEY_IN_USE`. This departs from the draft's SHOULD on purpose: clients get the answer instead of having to retry.
3. Repositories accept an `Engine` (one transaction per call, as before) or a `Connection` (join the caller's transaction); services that need atomicity across repositories use the unit of work.
4. The key is unique on its own; the fingerprint covers the operation (including the asset id for versions) and the request body, so reuse on another endpoint or asset is `422`.
5. Keys live 24 h (a key is live at exactly 24 h); expired keys are deleted on reuse and purged by the worker (KILN-22). A replay re-signs the upload form only while the version is still `pending_upload`.

## Consequences

- Waiting duplicates hold a pooled connection for up to 5 s; a retry storm with one key can use several connections. Acceptable for studio-scale traffic; revisit with rate limiting (KILN-12).
- Keys are global until KILN-12 adds the principal to the key.
- The atomicity is pinned by a test that crashes between the asset insert and completing the key.

## Sources

[IETF draft-ietf-httpapi-idempotency-key-header-08](https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/), `references/api-design.md` (idempotency), `references/data-and-reliability.md` (one transaction per use case, outbox).
