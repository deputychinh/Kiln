# KILN-28: Free a worker stuck on a hung job

- Release: v0.2 · Status: doing · Owner: Claude (deliver-loop)

## Story

As an **operator running Kiln workers**, I want a job that hangs (a stuck native call, a network read that never returns) to cost at most its time budget, so that one bad file cannot take a worker out of service until someone restarts it, and so that stopping a worker never waits forever.

Today (KILN-24/25) the heartbeat stops extending a hung job's lease after 30 minutes, so another worker can retry the job, but the worker running it stays blocked for good, and a stop request waits for that job without a bound.

INVEST: Independent ☑ (worker only) · Negotiable ☑ · Valuable ☑ · Estimable ☑ · Small ☑ · Testable ☑

## Acceptance criteria

| Id             | Given                                               | When                                                               | Then                                                                                                                                                                                                                  |
| -------------- | --------------------------------------------------- | ------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1            | a job still running at its maximum runtime (30 min) | the runtime is reached                                             | the worker process logs the job and version and exits at once with exit code 76 — even if the job is blocked in native code — before its lease (5 min longer) can expire, so no two workers ever run the job together |
| AC2            | a worker process exited with 76                     | the supervisor sees it                                             | it starts a fresh worker immediately (no crash backoff) and logs why; the job is retried by whichever worker claims it after its lease expires, and buried as `PROCESSING_GAVE_UP` after the usual 5 attempts         |
| AC3            | a stop is asked (SIGTERM / Ctrl-C) while a job runs | the job does not finish within the stop grace (60 s, configurable) | the worker exits with 76 after the grace instead of waiting; a job that finishes within the grace ends normally and the worker exits 0                                                                                |
| AC4            | the supervisor is stopping                          | its child does not exit within the grace + 10 s                    | the supervisor kills it and exits, so `docker stop` and process managers never hang                                                                                                                                   |
| AC5 (negative) | jobs that finish in time                            | they run                                                           | nothing is killed, the watchdog adds no measurable delay, and between jobs it does nothing                                                                                                                            |

## Non-functional

- Reliability: a hard exit loses nothing that matters — the database rolls back the dropped connection, the thumbnail is written in one PUT, the model sandbox child exits when its parent dies (KILN-5), and the job is retried through the existing attempts/bury path.
- Observability: one error line per overrun with job id, version id, attempt and runtime; the supervisor logs the restart reason.
- Security: none new (no new input, no new privileges).

## Out of scope

- One child process per job (spawn cost on every job; the per-process watchdog bounds a hang the same way).
- Releasing the lease early on overrun (the process may be wedged; expiry is the safe signal).

## References

- Release It! (Nygard), "Timeouts" and "Fail Fast"; `references/data-and-reliability.md` (timeouts on every blocking call, bounded shutdown).
- Kubernetes pod termination: SIGTERM, then SIGKILL after `terminationGracePeriodSeconds` (default 30 s): https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination
- Python `os._exit` (exits without cleanup, works while other threads are blocked): https://docs.python.org/3/library/os.html#os._exit
- sysexits.h: 75 EX_TEMPFAIL (recycle, KILN-25); 76 used here for "job overran".

## Design

- `kiln_worker/watchdog.py`: `JobWatchdog`, one daemon thread per worker process. `Worker.run_once` wraps each job in `watchdog.watch(job)`; the thread wakes at the job's deadline (max runtime) or when a stop is asked (then at stop + grace) and calls `exit(WORKER_OVERRAN_EXIT_CODE)` (`os._exit` by default) if the same job is still running. Clock, exit and logger are injectable for tests.
- Constants: `WORKER_OVERRAN_EXIT_CODE = 76`, `JOB_STOP_GRACE_SECONDS = 60`, `SUPERVISOR_KILL_MARGIN_SECONDS = 10`; setting `KILN_JOB_STOP_GRACE_SECONDS`.
- Supervisor: 76 restarts at once like 75 (with its own log line); on stop, `join(grace + margin)` then `kill()`.
- No API, data or UI change.

## QA

| AC  | Test(s)                                                                                                                                                                                                                                                                                                                                                                       | Result |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| AC1 | `test_watchdog.py`: a job past its runtime exits with 76 and logs job, version, attempt and budget; a real subprocess blocked in `select()` (native code) ends with 76 in well under 10 s; `test_runner.py` "a hung job ends the worker process through its watchdog" (real database, a download that never returns) — mutation: not wrapping the job in the watchdog → fails | pass   |
| AC2 | `test_supervisor.py` "a worker ended by its watchdog is replaced at once" (no backoff, crash count reset, logged); retry/bury after attempts is the existing KILN-24 path (`_job_status` attempt count)                                                                                                                                                                       | pass   |
| AC3 | `test_watchdog.py`: after a stop the job gets its grace then the process ends with 76; a job finishing within the grace ends normally; a stop asked before the job counts from the job start                                                                                                                                                                                  | pass   |
| AC4 | `test_supervisor.py`: a child that ignores SIGTERM is joined for grace + 10 s, then killed (mutation: no kill → fails); a child that ends in time is not killed                                                                                                                                                                                                               | pass   |
| AC5 | `test_watchdog.py` "a job that finishes in time is left alone" (an hour later nothing fires); the whole worker suite (264 tests) runs unchanged with the watchdog wired                                                                                                                                                                                                       | pass   |
