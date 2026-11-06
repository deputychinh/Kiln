# KILN-24: Lease heartbeat for long worker jobs

- Release: v0.1 · Status: doing · Owner: Claude (deliver-loop)

## Story

As the **person running a Kiln studio server**, I want a job that legitimately takes longer than its 5-minute lease (a large texture, a slow storage download, later a 3D render) to keep its lease while it is making progress, so that a second worker does not start the same job, double the work and burn an attempt — while a job that hangs still gets released.

INVEST: Independent ☑ (KILN-4 queue) · Negotiable ☑ · Valuable ☑ · Estimable ☑ · Small ☑ (one queue method, one helper thread) · Testable ☑

## Acceptance criteria

| Id                | Given                                                                                   | When                               | Then                                                                                                                                                                                                                                                                                 |
| ----------------- | --------------------------------------------------------------------------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| AC1               | a worker processing a claimed job                                                       | the job runs longer than the lease | the worker extends the lease every third of the lease (100 s) to `now() + lease` (database clock); another worker polling meanwhile does not claim it; the job finishes `done` with one attempt                                                                                      |
| AC2               | the job finishes, fails or raises                                                       | processing ends                    | the heartbeat is stopped before the outcome is written (no extension races the write, so a refusal is never mistaken for a lost claim) and its thread is joined, waiting at most 10 s for an extension in flight                                                                     |
| AC3 (negative)    | the claim was lost (lease expired and another worker re-claimed, or the job was buried) | the heartbeat tries to extend      | the extension is refused by the claim guard (`status = running` and the attempt number) — and an already-expired lease is never extended, since another worker may be reclaiming or burying it — the heartbeat stops and logs a warning once; the outcome write is refused as before |
| AC4 (hung job)    | a job still running after 30 minutes                                                    | the heartbeat ticks                | it stops extending and logs a warning with the job id, so the lease expires and the job is retried or buried like a crashed one                                                                                                                                                      |
| AC5 (reliability) | the database is briefly unavailable                                                     | the heartbeat ticks                | the failed extension is logged with a stable cause (`DATABASE_UNAVAILABLE`) and retried at the next tick; the job keeps running; connecting gives up after 5 s (`connect_timeout`)                                                                                                   |

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

| AC  | Test(s)                                                                                                                                                                                                                                                                                                                                                           | Result |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| AC1 | `worker/tests/test_runner.py` "a job longer than its lease is kept by the heartbeat and not taken twice" (real database clock, 1 s lease, 2.5 s render, a second worker polling); `api/tests/db/test_job_queue.py` "extending moves the lease and keeps the job running"; `worker/tests/test_heartbeat.py` "a running job extends its lease until the block ends" | pass   |
| AC2 | `worker/tests/test_runner.py` "the heartbeat stops before the outcome is written" (no extension after `finish`, no false warning); `worker/tests/test_heartbeat.py` "leaving the block waits for an extension in flight", "waiting for a stuck extension is bounded and logged", "stopping twice is harmless"                                                     | pass   |
| AC3 | `api/tests/db/test_job_queue.py` "a stale claim cannot extend a reclaimed or finished job", "an expired lease is never extended even if nobody reclaimed it"; `worker/tests/test_heartbeat.py` "a refused extension means the lease is lost and stops the heartbeat", "a refusal after the job finished is not reported as a lost claim"                          | pass   |
| AC4 | `worker/tests/test_heartbeat.py` "a hung job stops being extended after the maximum runtime"                                                                                                                                                                                                                                                                      | pass   |
| AC5 | `worker/tests/test_heartbeat.py` "a database hiccup is logged and the next tick extends again", "database errors are logged with a stable code"; `api/tests/db/test_container.py` "the engine gives up connecting after a few seconds"                                                                                                                            | pass   |

Gates (round 2): `make ci` green — Python 451 passed (99 %), ui 16, web 89; `make e2e` 12 passed.

Mutation checks (`PYTHONDONTWRITEBYTECODE=1`, each reverted). Round 1: 5 of 6 killed; the claim that the stop-and-join mutant was killed was wrong (a test slept before checking the thread, so a missing join passed). Round 2: 6 of 6 killed — expired-lease guard, bounded join, silent refusal after stop, stable database cause, stop before `finish` (killed only after the runner test was made deterministic by holding the window open after `finish`), connect timeout.

## Review rounds

- Round 1 (independent reviewer): 8.5/10 — an expired, unreclaimed lease could be extended while another worker buried the job as exhausted (reproduced on the real database); a refused tick right after a normal finish was reported as "lease lost" (19 of 20 jobs with a 0.5 ms interval); the join had no bound and the engine no connect timeout; a test could not catch a missing join, so the story's mutation claim was wrong; raw driver class names in logs; a hung job keeps its worker blocked (filed as KILN-28). All fixed in round 2.

## Review score

| #   | Criterion | Score | Evidence |
| --- | --------- | ----- | -------- |
