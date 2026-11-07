# ADR 0012: One workspace in v0.2, one authorization policy for every check

- Status: accepted · 2026-11-08

## Context

KILN-12 adds users. Kiln v0.2 serves one studio per deployment (5–50 people) where everyone reviews everyone's work; leads approve assets they did not upload (KILN-11). Per-user privacy would block that. A hosted, multi-studio Kiln is possible later, and OWASP API1:2023 (Broken Object Level Authorization) is the most common API flaw when such checks are scattered over handlers.

## Decision

1. **Single workspace.** Every signed-in user can read and change every asset. Each asset records its `owner_id` and each version its `uploaded_by` (nullable only for rows made before sign-in), ready for annotations, comments and approvals (KILN-10, KILN-11).
2. **One policy.** `kiln_api/domain/authorization.py` is the only place that decides: `authorize(principal, action, asset=None)` and `visible_owner(principal)` for listings. Every asset use case calls it, with the loaded asset when there is one (`get`, `get_version`, `add_version` under the asset's row lock, `complete_upload`). A later tenant model changes `_in_workspace` and `visible_owner`, nothing else; out-of-workspace assets answer 404, not 403, so ids do not leak.
3. **Scopes.** A browser session has every scope. A personal access token has `read`, `write` or both: reads need `read`, writes need `write` (403 `INSUFFICIENT_SCOPE`). Managing tokens needs a browser session (403 `SESSION_REQUIRED`), so a leaked token cannot mint more.
4. **Idempotency keys are per user** (migration 0007, as ADR 0006 promised): `(user_id, key)` is the key, so one user's key never replays another user's response.

## Consequences

- No per-user privacy in v0.2; the story and the README say so. A user cannot be deleted while they own assets (the foreign keys have no cascade), which keeps authorship; deactivation is a later item.
- The policy is tested on its own (`test_authorization.py`) and through the API (`test_a_read_token_cannot_write_assets_bola`); `test_every_route_needs_a_principal_except_health_and_sign_in` walks the OpenAPI document so a new route without a principal fails CI.
- Keys made before migration 0007 are dropped (they lived 24 h at most).

## Sources

OWASP API Security Top 10:2023 API1 (BOLA) and API5 (BFLA); OWASP ASVS 5.0 V8 Authorization; `references/backend-architecture.md` (authorize in the service, per object).
