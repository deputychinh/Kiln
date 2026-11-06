# KILN-23: Circuit breaker and bulkhead around storage calls

- Release: v0.1 · Status: doing · Owner: Claude (deliver-loop)

## Story

As the **person running a Kiln studio server**, I want the API to stop waiting on object storage once storage is clearly down, and to cap how many requests can wait on it at once, so that a storage outage gives fast, honest errors instead of exhausting the API's worker threads and making every page slow — including pages that do not need storage.

INVEST: Independent ☑ (wraps the existing storage port) · Negotiable ☑ · Valuable ☑ · Estimable ☑ · Small ☑ (one decorator, settings, one header) · Testable ☑

## Acceptance criteria

| Id             | Given                                                                                                                                         | When                                                                                                          | Then                                                                                                                                                                                    |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1            | storage fails 5 times in a row (timeouts, 5xx, connection errors)                                                                             | the next storage call is made                                                                                 | the circuit opens: calls fail immediately (no network) with 503 `STORAGE_UNAVAILABLE` and `Retry-After` = the seconds left of a 30 s cool-down; a warning is logged once with the cause |
| AC2            | the circuit is open and the cool-down has passed                                                                                              | requests arrive                                                                                               | exactly one trial call goes to storage (half-open); success closes the circuit (logged), failure reopens it for another cool-down; other calls keep failing fast meanwhile              |
| AC3 (edge)     | failures interleaved with successes                                                                                                           | calls are made                                                                                                | only consecutive failures count; any success resets the count; "not found" and "changed" results are answers, not failures                                                              |
| AC4 (bulkhead) | 16 storage calls already in flight                                                                                                            | another request needs storage                                                                                 | it waits at most 0.5 s for a slot, then fails with 503 `STORAGE_UNAVAILABLE` and `Retry-After: 1`; bulkhead rejections do not open the circuit                                          |
| AC5            | the circuit is open                                                                                                                           | a request that only signs URLs (the gallery list and asset detail sign previews locally) or `/health` is made | it is served normally; signing URLs (local, no network) is never blocked                                                                                                                |
| AC6            | the circuit is open                                                                                                                           | `GET /ready`                                                                                                  | answers 503 at once (readiness reflects the circuit)                                                                                                                                    |
| AC7 (config)   | `KILN_STORAGE_BREAKER_FAILURES`, `KILN_STORAGE_BREAKER_COOLDOWN_SECONDS`, `KILN_STORAGE_MAX_CONCURRENT`, `KILN_STORAGE_BULKHEAD_WAIT_SECONDS` | the process starts                                                                                            | they are read and validated (> 0); defaults 5, 30, 16, 0.5                                                                                                                              |

## Non-functional

- Reliability: thread-safe (sync endpoints run in a thread pool); the state machine uses a monotonic clock; the breaker wraps every network call of the storage port (head, promote, delete, download, upload, ping, ensure-bucket, listing) in API and worker.
- Security: error bodies unchanged (no internal cause leaked; the cause code — `CIRCUIT_OPEN`, `BULKHEAD_FULL` — goes to logs only).
- Performance: an open circuit answers in microseconds instead of the 3 s connect + 10 s read timeouts × 2 attempts.

## Out of scope

- A database circuit breaker (the pool and statement timeouts already bound it), per-endpoint bulkheads, metrics endpoint, adaptive concurrency limits.

## References

- Nygard, _Release It!_ 2nd ed., ch. 5 "Stability Patterns": Circuit Breaker, Bulkheads, Fail Fast.
- Microsoft Azure Architecture Center — Circuit Breaker pattern (closed / open / half-open): https://learn.microsoft.com/azure/architecture/patterns/circuit-breaker
- Resilience4j CircuitBreaker and Bulkhead (count-based window, semaphore bulkhead with max wait): https://resilience4j.readme.io/docs/circuitbreaker, https://resilience4j.readme.io/docs/bulkhead
- RFC 9110 §10.2.3 `Retry-After`: https://www.rfc-editor.org/rfc/rfc9110#field.retry-after
- `references/data-and-reliability.md` (timeouts, retries, circuit breakers).

## Design

- `kiln_api/resilience.py`: `CircuitBreaker` (closed → open after N consecutive failures → half-open after the cool-down, one trial at a time) and `GuardedStorage`, an `ObjectStorage` decorator adding the breaker and a semaphore bulkhead to network calls; presigning passes through.
- `StorageUnavailableError` carries an optional `retry_after_seconds`; the problem handler sends it as `Retry-After` (default 1 s as today).
- `build_container` and the worker wrap `build_storage(settings)` with `guard_storage(settings)`; settings validated with `gt=0`.

## QA

| AC  | Test(s)                                                                                                                                                                                                                                                                                                                                                                                                                                                                | Result |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| AC1 | `unit/test_resilience.py` "the circuit opens after consecutive failures and fails fast with the cooldown left" (warning once, `Retry-After` = ceil of the time left), "storage failures open the circuit and then storage is not called"; `api/test_storage_resilience_api.py` "an open circuit answers 503 at once with the cooldown as retry after"; `integration/test_s3_storage.py` "a storage endpoint that refuses connections opens the circuit" (real network) | pass   |
| AC2 | `unit/test_resilience.py` "after the cooldown one trial goes through and success closes", "a failed trial reopens for a full cooldown without logging again", "releasing a trial without a verdict lets the next call try", "a listing failure counts and an early stop frees the trial"                                                                                                                                                                               | pass   |
| AC3 | `unit/test_resilience.py` "only consecutive failures count", "answers like not found or changed are successes", "a bug in a call is not counted against storage"                                                                                                                                                                                                                                                                                                       | pass   |
| AC4 | `unit/test_resilience.py` "a full bulkhead rejects after the wait without opening the circuit", "a call waits for a slot that frees up within the wait", "a trial turned away by the bulkhead lets the next call try"                                                                                                                                                                                                                                                  | pass   |
| AC5 | `unit/test_resilience.py` "signing is local and never blocked by an open circuit"; `api/test_storage_resilience_api.py` "with the circuit open ready fails and pages that only sign urls still work" (list, create)                                                                                                                                                                                                                                                    | pass   |
| AC6 | `api/test_storage_resilience_api.py` same test (`/ready` 503, `/health` 200)                                                                                                                                                                                                                                                                                                                                                                                           | pass   |
| AC7 | `unit/test_resilience.py` "resilience settings must be positive" (4 settings); `api/test_storage_resilience_api.py` "the container guards real storage by default"; `.env.example`                                                                                                                                                                                                                                                                                     | pass   |

Also: `unit/test_resilience.py` "every network call goes through the guard" (8 calls fail through the guard; presigning does not).

Gates: `make ci` green — Python 420 passed (99 %), ui 16, web 89; `make e2e` 12 passed; mutation checks (`PYTHONDONTWRITEBYTECODE=1`, each reverted): 13 of 13 killed after adding tests for three first-pass survivors — rounding of `Retry-After` (now a value where `round` and `ceil` differ), freeing a half-open trial turned away by the bulkhead, and waiting for a slot instead of failing at once.

## Review score

| #   | Criterion | Score | Evidence |
| --- | --------- | ----- | -------- |
