# KILN-21: Idempotency-Key for creating assets and versions

- Release: v0.1 · Status: todo (BA done) · Owner: Claude (deliver-loop)

## Story

As an **artist on a flaky studio network** (or the Blender add-on and CLI retrying for me), I want to resend a "create asset" or "add version" request safely, so that a timeout never leaves me with duplicate assets or version numbers I did not intend.

INVEST: Independent ☑ (builds on KILN-3) · Negotiable ☑ · Valuable ☑ · Estimable ☑ · Small ☑ (one table, one middleware-like helper, two endpoints) · Testable ☑

## Acceptance criteria

| Id             | Given                                                                                                          | When                                                         | Then                                                                                                                                                                                                |
| -------------- | -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1            | a `POST /api/v1/assets` with header `Idempotency-Key: "<uuid>"` that succeeded                                 | the same request with the same key is sent again within 24 h | `201` with the same asset and version ids and the same `Location`, header `Idempotent-Replayed: true`, a freshly signed `upload` form (signatures are not side effects), and no second asset exists |
| AC2            | the same as AC1 for `POST /api/v1/assets/{id}/versions`                                                        | resent                                                       | the same version number is returned; no extra version is created                                                                                                                                    |
| AC3 (negative) | a key already used with a different body or a different path                                                   | the request is sent                                          | `422` problem details with `IDEMPOTENCY_KEY_REUSED`; nothing is created                                                                                                                             |
| AC4 (negative) | a request with the key is still in progress                                                                    | a duplicate arrives                                          | `409` with `IDEMPOTENCY_KEY_IN_USE`; the client may retry without changes                                                                                                                           |
| AC5 (edge)     | a header that is not a valid key (empty, over 255 characters, non-printable characters, a malformed sf-string) | any of the two POSTs                                         | `400` with `INVALID_IDEMPOTENCY_KEY`                                                                                                                                                                |
| AC6            | no `Idempotency-Key` header                                                                                    | any of the two POSTs                                         | the request is processed normally (the key is optional in v0.1; the CLI and add-on always send one)                                                                                                 |
| AC7            | a request with a key that failed with a client error (4xx from validation or a domain rule)                    | the corrected request is sent with the same key              | it is processed as new (failures are not stored), so a client can fix and retry                                                                                                                     |
| AC8            | a key older than 24 h                                                                                          | reused                                                       | it is treated as new; expired keys are purged by the purge function (scheduled by the worker in KILN-4)                                                                                             |

## Non-functional

- Reliability: the key row and the created asset/version are written in **one transaction**, so a crash cannot store one without the other; concurrent duplicates are serialised by the primary key `(scope, key)`.
- Security: keys are scoped by method + path, and in v0.2 by principal (KILN-12), so one client cannot replay another's response; request bodies are stored only as a SHA-256 hash; stored responses contain no secrets (the signed form is regenerated, never stored).
- API: header syntax per the IETF draft (an sf-string, e.g. `"8e03978e-40d5-43e8-bc93-6894a57f9324"`); unquoted tokens are accepted for tolerance; the expiry policy (24 h) is published in the OpenAPI description.

## Out of scope

- Requiring the key (v0.2 once clients send it), idempotency for completions (already idempotent by state), scheduling the purge (KILN-4).

## References

- IETF draft-ietf-httpapi-idempotency-key-header-08 (22 Oct 2026): 400 for a missing/invalid key, 422 for reuse with a different payload, 409 while the first request is in progress, sf-string syntax, published expiry: https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/
- Vendor practice (Ripple, Gotitus): replay the original status and body; do not cache failures so clients can correct and retry: https://docs.ripple.com/products/collections/guides/idempotency, https://docs.gotitus.com/guide/developer-resources/idempotency
- `references/api-design.md` (idempotency MUST), `references/data-and-reliability.md` (one transaction per use case).

## Design

- **Table** `idempotency_keys(scope text, key text, request_hash bytea(32), status_code int, response jsonb, created_at timestamptz, PRIMARY KEY (scope, key))`, migration `0002_idempotency_keys`, index on `created_at` for the purge.
- **Flow** (service layer, one transaction with the creation): `INSERT … ON CONFLICT DO NOTHING` a row marked in progress (`status_code` NULL); on conflict, read the row: different hash → 422; `status_code` NULL → 409; else replay. On success, store status and response body (without `upload`), commit together with the asset. On a domain error the transaction rolls back, so the key is not stored (AC7).
- **Replay**: rebuild the response from the stored ids (re-read asset and version) and sign a new upload form.
- **Port** `IdempotencyStore` with a Postgres adapter; the repository and the store share one connection per use case via a unit-of-work.
