# KILN-24: Lease heartbeat for long worker jobs

- Release: v0.1 · Status: done · Owner: Claude (deliver-loop)

## Story

As the **person running a Kiln studio server**, I want a job that legitimately takes longer than its 5-minute lease (a large texture, a slow storage download, later a 3D render) to keep its lease while it is making progress, so that a second worker does not start the same job, double the work and burn an attempt — while a job that hangs still gets released.

INVEST: Independent ☑ (KILN-4 queue) · Negotiable ☑ · Valuable ☑ · Estimable ☑ · Small ☑ (one queue method, one helper thread) · Testable ☑

## Acceptance criteria

| Id                | Given                                                                                   | When                               | Then                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ----------------- | --------------------------------------------------------------------------------------- | ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1               | a worker processing a claimed job                                                       | the job runs longer than the lease | the worker extends the lease every third of the lease (100 s) to `now() + lease` (database clock); another worker polling meanwhile does not claim it; the job finishes `done` with one attempt                                                                                                                                                                                                                                                                                                                                                                                                                   |
| AC2               | the job finishes, fails or raises                                                       | processing ends                    | the heartbeat is stopped before the outcome is written (no extension races the write, so a refusal is never mistaken for a lost claim) and its thread is joined, waiting for an extension in flight at most 20 s — longer than any statement may run (15 s), so the outcome write never queues behind it                                                                                                                                                                                                                                                                                                          |
| AC3 (negative)    | the claim was lost (lease expired and another worker re-claimed, or the job was buried) | the heartbeat tries to extend      | the extension is refused by the claim guard (`status = running` and the attempt number) — and a lease is not extended once another worker has reclaimed or reaped the job (an expired lease is refused; a writer that changes the row while the extension waits on its lock is caught by the claim guard on Postgres's re-check) — the heartbeat stops and logs once that the lease expired or was taken over; the outcome write is refused as before. A worker reaping exhausted jobs buries one only if its lease is still expired at the moment of the write, so a job its owner just extended is never buried |
| AC4 (hung job)    | a job still running after 30 minutes                                                    | the heartbeat ticks                | it stops extending and logs a warning with the job id, so the lease expires and the job is retried or buried like a crashed one                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| AC5 (reliability) | the database is briefly unavailable                                                     | the heartbeat ticks                | the failed extension is logged with a stable cause (`DATABASE_UNAVAILABLE`) and retried at the next tick; the job keeps running; connecting gives up after 5 s (`connect_timeout`)                                                                                                                                                                                                                                                                                                                                                                                                                                |

## Non-functional

- Reliability: extensions are guarded by the claim exactly like `finish`/`retry`/`bury`; lease times use the database clock; the heartbeat is a daemon thread joined when the job ends.
- Observability: log lines carry the job id only (no names).
- Performance: one small `UPDATE` per 100 s per running job.

## Out of scope

- Freeing a worker stuck on a hung job (its lease is released after about 35 minutes, but that worker stays blocked) → **KILN-28** (v0.2).
- Cancelling the work of a job whose lease was lost (the outcome write is already refused; the thumbnail key is deterministic, so a duplicate upload is harmless), progress reporting, per-kind runtimes.

## References

- Kleppmann, _Designing Data-Intensive Applications_, ch. 8 "The Truth Is Defined by the Majority" — leases, process pauses and fencing tokens (the attempt number is our fencing token).
- Amazon SQS `ChangeMessageVisibility` heartbeat for long-running consumers: https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html
- Google Cloud Tasks / Pub/Sub lease extension (`modifyAckDeadline`): https://cloud.google.com/pubsub/docs/lease-management
- `references/data-and-reliability.md` (idempotent consumers, leases).

## Design

- `JobQueue.extend(job, *, lease, now=None) -> bool` in `SqlJobQueue`: `UPDATE … SET leased_until = now() + lease WHERE id AND status = 'running' AND attempts = :claimed`.
- `kiln_worker/heartbeat.py` `LeaseHeartbeat` context manager: a thread that waits `interval`, stops at exit, on a refused extension, or after `max_runtime`; logs and keeps going on errors.
- `Worker._handle` runs the job inside the heartbeat; lease, interval and maximum runtime are constructor parameters (defaults from constants) so tests can use short ones.

## QA

| AC  | Test(s)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | Result |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| AC1 | `worker/tests/test_runner.py` "a job longer than its lease is kept by the heartbeat and not taken twice" (real database clock, 1 s lease, 2.5 s render, a second worker polling); `api/tests/db/test_job_queue.py` "extending moves the lease and keeps the job running"; `worker/tests/test_heartbeat.py` "a running job extends its lease until the block ends"                                                                                                                                                                                                               | pass   |
| AC2 | `worker/tests/test_runner.py` "the heartbeat stops before the outcome is written", "the heartbeat also stops before a retry or a skip is written" (retry / close) (no extension after `finish`, no false warning); `worker/tests/test_heartbeat.py` "leaving the block waits for an extension in flight", "waiting for a stuck extension is bounded and logged", "stopping twice is harmless"                                                                                                                                                                                   | pass   |
| AC3 | `api/tests/db/test_job_queue.py` "a stale claim cannot extend a reclaimed or finished job", "an expired lease is never extended even if nobody reclaimed it", "a reaper never buries a job whose lease was extended after it looked", "a reaper buries a job whose lease is still expired"; `worker/tests/test_runner.py` "the reaper leaves a job whose owner extended it after the reaper looked"; `worker/tests/test_heartbeat.py` "a refused extension means the lease is lost and stops the heartbeat", "a refusal after the job finished is not reported as a lost claim" | pass   |
| AC4 | `worker/tests/test_heartbeat.py` "a hung job stops being extended after the maximum runtime"                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | pass   |
| AC5 | `worker/tests/test_heartbeat.py` "a database hiccup is logged and the next tick extends again", "database errors are logged with a stable code", "an extension failing after the job ended is not logged"; `api/tests/db/test_container.py` "the engine gives up connecting after a few seconds"                                                                                                                                                                                                                                                                                | pass   |

Gates (round 3): `make ci` green — Python 457 passed (99 %), ui 16, web 89; `make e2e` 12 passed.

Mutation checks (`PYTHONDONTWRITEBYTECODE=1`, each reverted). Round 1: 5 of 6 killed; the claim that the stop-and-join mutant was killed was wrong (a test slept before checking the thread, so a missing join passed). Round 2: 6 of 6 killed — expired-lease guard, bounded join, silent refusal after stop, stable database cause, stop before `finish` (killed only after the runner test was made deterministic by holding the window open after `finish`), connect timeout. Round 3: 8 of 8 killed after two added tests — reap's expiry guard, the runner reaping (not burying) exhausted jobs, stop before retry, stop before close, silence after stop, domain error codes.

## Review rounds

- Round 1 (independent reviewer): 8.5/10 — an expired, unreclaimed lease could be extended while another worker buried the job as exhausted (reproduced on the real database); a refused tick right after a normal finish was reported as "lease lost" (19 of 20 jobs with a 0.5 ms interval); the join had no bound and the engine no connect timeout; a test could not catch a missing join, so the story's mutation claim was wrong; raw driver class names in logs; a hung job keeps its worker blocked (filed as KILN-28). All fixed in round 2.

- Round 2 (fresh reviewer): 8.5/10 — a reaper could still bury a job whose lease was extended between its read and its write (reproduced with an open transaction); no test proved the heartbeat stops before a retry or a skip; "lease lost" wording when the lease merely expired; an extension failing after the job ended was still logged; domain errors logged by class name. Fixed in round 3: `JobQueue.reap` buries only while the lease is still expired; tests for retry and close; reworded logs; silence after stop; `DomainError.code` in logs.

- Round 3 (fresh reviewer, final gate): **9.5/10, pass**. Interleavings forced on a scratch database (owner extends in an open transaction while the reaper waits; reap first; reclaim first; 8 owners × 4 reapers × 40 jobs with a 1 s lease: all done, none lost or reaped). After the gate: the join now outlasts the statement timeout (20 s), and the story's "never extended" wording was narrowed — a test showed Postgres re-checks a lock-waiting update only when the row changed, so the claim guard (not a later clock) is what refuses it. Accepted smells: `LeaseHeartbeat.lost` is only read by tests; `_give_up(reaping=…)` is a flag argument.

## Review score

| #   | Criterion        | Score      | Evidence (reviewer, round 3)                                                              |
| --- | ---------------- | ---------- | ----------------------------------------------------------------------------------------- |
| 1   | Requirements fit | 1          | AC1–AC5 traced to passing tests; KILN-28 filed for the hung-worker case                   |
| 2   | Test depth       | 1          | 9/9 reviewer mutants killed; timing tests stable over 9 runs, 3 under CPU load            |
| 3   | Reliability      | 1          | forced interleavings and a 40-job multi-worker probe: nothing lost, reaped or taken twice |
| 4   | Security         | 1          | logs carry the job id and an error code only                                              |
| 5   | Maintainability  | 0.5        | `lost` read only by tests; flag argument `reaping`                                        |
| 6   | API ergonomics   | 1          | `extend`/`reap` follow the guarded `_set` pattern                                         |
| 7   | Accessibility    | 1          | no UI change                                                                              |
| 8   | Performance      | 1          | one primary-key update per 100 s per running job                                          |
| 9   | Docs             | 1          | story, CHANGELOG, architecture, backlog                                                   |
| 10  | Delivery         | 1          | gates green, pushed, clean tree                                                           |
|     | **Total**        | **9.5/10** | reviewer: fresh subagent, round 3 (rounds 1–2: 8.5, 8.5)                                  |
