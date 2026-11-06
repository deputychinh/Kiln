# KILN-24: Lease heartbeat for long worker jobs

- Release: v0.1 · Status: doing · Owner: Claude (deliver-loop)

## Story

As the **person running a Kiln studio server**, I want a job that legitimately takes longer than its 5-minute lease (a large texture, a slow storage download, later a 3D render) to keep its lease while it is making progress, so that a second worker does not start the same job, double the work and burn an attempt — while a job that hangs still gets released.

INVEST: Independent ☑ (KILN-4 queue) · Negotiable ☑ · Valuable ☑ · Estimable ☑ · Small ☑ (one queue method, one helper thread) · Testable ☑

## Acceptance criteria

| Id                | Given                                                                                   | When                               | Then                                                                                                                                                                                            |
| ----------------- | --------------------------------------------------------------------------------------- | ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1               | a worker processing a claimed job                                                       | the job runs longer than the lease | the worker extends the lease every third of the lease (100 s) to `now() + lease` (database clock); another worker polling meanwhile does not claim it; the job finishes `done` with one attempt |
| AC2               | the job finishes, fails or raises                                                       | processing ends                    | the heartbeat stops at once (no extension after the outcome is written; no thread left behind)                                                                                                  |
| AC3 (negative)    | the claim was lost (lease expired and another worker re-claimed, or the job was buried) | the heartbeat tries to extend      | the extension is refused by the claim guard (`status = running` and the attempt number), the heartbeat stops and logs a warning once; the outcome write is refused as before                    |
| AC4 (hung job)    | a job still running after 30 minutes                                                    | the heartbeat ticks                | it stops extending and logs a warning with the job id, so the lease expires and the job is retried or buried like a crashed one                                                                 |
| AC5 (reliability) | the database is briefly unavailable                                                     | the heartbeat ticks                | the failed extension is logged with its cause and retried at the next tick; the job keeps running                                                                                               |

## Non-functional

- Reliability: extensions are guarded by the claim exactly like `finish`/`retry`/`bury`; lease times use the database clock; the heartbeat is a daemon thread joined when the job ends.
- Observability: log lines carry the job id only (no names).
- Performance: one small `UPDATE` per 100 s per running job.

## Out of scope

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

| AC  | Test(s)                                                                                                                                                                                                                                                                                                                                                           | Result |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| AC1 | `worker/tests/test_runner.py` "a job longer than its lease is kept by the heartbeat and not taken twice" (real database clock, 1 s lease, 2.5 s render, a second worker polling); `api/tests/db/test_job_queue.py` "extending moves the lease and keeps the job running"; `worker/tests/test_heartbeat.py` "a running job extends its lease until the block ends" | pass   |
| AC2 | `worker/tests/test_heartbeat.py` "a running job extends its lease until the block ends" (no extension after exit, no thread left)                                                                                                                                                                                                                                 | pass   |
| AC3 | `api/tests/db/test_job_queue.py` "a stale claim cannot extend a reclaimed or finished job"; `worker/tests/test_heartbeat.py` "a refused extension means the lease is lost and stops the heartbeat" (warning once)                                                                                                                                                 | pass   |
| AC4 | `worker/tests/test_heartbeat.py` "a hung job stops being extended after the maximum runtime"                                                                                                                                                                                                                                                                      | pass   |
| AC5 | `worker/tests/test_heartbeat.py` "a database hiccup is logged and the next tick extends again"                                                                                                                                                                                                                                                                    | pass   |

Gates: `make ci` green — Python 443 passed (99 %), ui 16, web 89; `make e2e` 12 passed.

Mutation checks (`PYTHONDONTWRITEBYTECODE=1`, each reverted): 6 of 6 killed — heartbeat removed from the runner, maximum-runtime stop, stop on a lost claim, continue after an error, stop-and-join on exit, the extension's `+ lease`.

## Review score

| #   | Criterion | Score | Evidence |
| --- | --------- | ----- | -------- |
