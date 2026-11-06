# KILN-25: Recycle the worker process

- Release: v0.1 · Status: doing · Owner: Claude (deliver-loop)

## Story

As the **person running a Kiln studio server**, I want each worker process replaced by a fresh one after a number of jobs or once its memory grows past a limit, so that memory Pillow keeps mapped after large images (a 50 MP PNG peaks at ~220 MB and is not returned to the OS) does not accumulate until the machine swaps or the process is OOM-killed mid-job.

INVEST: Independent ☑ (wraps the KILN-4 loop) · Negotiable ☑ · Valuable ☑ · Estimable ☑ · Small ☑ (a policy, a supervisor, settings) · Testable ☑

## Acceptance criteria

| Id             | Given                                                                              | When                        | Then                                                                                                                                 |
| -------------- | ---------------------------------------------------------------------------------- | --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| AC1            | a worker that has finished `KILN_WORKER_MAX_JOBS` jobs (default 200)               | it would claim the next one | it stops claiming, logs why (jobs done, peak memory), exits with the recycle code, and the supervisor starts a fresh process at once |
| AC2            | a worker whose peak resident memory passed `KILN_WORKER_MAX_RSS_MB` (default 1024) | a job finishes              | it recycles the same way after that job (never in the middle of one)                                                                 |
| AC3            | the supervisor receives SIGTERM/SIGINT (or `stop`)                                 | a child is running          | the child gets SIGTERM, finishes its current job, and the supervisor exits 0 once it has; no new child starts                        |
| AC4 (negative) | a child crashes (non-zero exit other than the recycle code, or killed)             | the supervisor notices      | it logs the exit code and starts a new child after a backoff of 1, 2, 4 … s capped at 30 s; a clean recycle resets the backoff       |
| AC5 (config)   | the two settings                                                                   | the process starts          | they are validated (> 0) and listed in `.env.example`                                                                                |

## Non-functional

- Reliability: jobs are never cut short by recycling (checked between jobs only); a child killed mid-job loses nothing — its lease expires and the job is retried (KILN-4/24).
- Portability: peak RSS from `resource.getrusage` (bytes on macOS, KiB on Linux, normalised); child processes use the `spawn` start method, so nothing (database connections, threads) is inherited.
- Observability: one line per recycle and per restart, with counts and codes only.

## Out of scope

- Several children per supervisor (run more containers instead), a health endpoint for the supervisor, killing a hung job's child (KILN-28).

## References

- Gunicorn `max_requests` / Celery `worker_max_tasks_per_child` and `worker_max_memory_per_child` — the standard answer to allocator fragmentation in long-running Python workers: https://docs.celeryq.dev/en/stable/userguide/workers.html#max-tasks-per-child-setting, https://docs.gunicorn.org/en/stable/settings.html#max-requests
- Pillow memory management and why freed image memory is often not returned: https://pillow.readthedocs.io/en/stable/reference/block_allocator.html
- Python `multiprocessing` start methods (`spawn`): https://docs.python.org/3/library/multiprocessing.html#contexts-and-start-methods
- `references/data-and-reliability.md` (bounded resources, supervision).

## Design

- `kiln_worker/recycle.py`: `RecyclePolicy(max_jobs, max_rss_bytes)` and `peak_rss_bytes()`; `Worker.run(..., recycle=policy)` returns `RunEnd.STOPPED` or `RunEnd.RECYCLE`.
- `kiln_worker/supervisor.py`: `Supervisor(start_child, stop)` restarts children: recycle → at once, crash → backoff, stop → SIGTERM and join.
- `kiln_worker/__main__.py`: `run_worker(settings, options, stop)` is the child's body (exit code 0 or 75 = recycle); `main()` runs the supervisor with `spawn` children.

## QA

| AC  | Test(s)                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | Result |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------ |
| AC1 | `worker/tests/test_runner.py` "run recycles between jobs after the policy says so" (2 of 3 jobs done, the third still queued, log line); `worker/tests/test_recycle.py` "the job count and peak memory decide when to recycle"; `worker/tests/test_main.py` "a worker that should recycle exits with the recycle code", "a spawned child exits with the worker's code"; `worker/tests/test_supervisor.py` "recycled workers are replaced at once and a stop ends the last one" | pass   |
| AC2 | `worker/tests/test_recycle.py` same test (memory limit, at-the-limit kept), "peak memory is reported in bytes on every platform", "the real peak memory is plausible"; `worker/tests/test_runner.py` "run recycles between jobs…" (checked after a job only)                                                                                                                                                                                                                   | pass   |
| AC3 | `worker/tests/test_main.py` "python -m kiln worker starts a child that works and stops on sigterm" (the real command as a subprocess), "sigterm stops the supervisor and its spawned worker" (a real `spawn` child); `worker/tests/test_supervisor.py` "recycled workers are replaced at once and a stop ends the last one" (terminate + join), "no child starts once stop was asked"; `worker/tests/test_runner.py` "run without a policy keeps working until asked to stop"  | pass   |
| AC4 | `worker/tests/test_supervisor.py` "a crashing worker is restarted with a growing backoff" (1, 2, 4, 8, 16, 30, 30, reset by a recycle; exit codes logged), "a child stopped directly ends the supervisor"                                                                                                                                                                                                                                                                      | pass   |
| AC5 | `worker/tests/test_main.py` "recycle settings must be positive", "the worker guards its storage and passes the recycle policy"; `.env.example`                                                                                                                                                                                                                                                                                                                                 | pass   |

Gates: `make ci` green — Python 472 passed (99 %), ui 16, web 89; `make e2e` 12 passed (the e2e worker now runs through the supervisor and a spawned child).

Mutation checks (each reverted, `PYTHONDONTWRITEBYTECODE=1`): 10 of 10 killed — job and memory boundaries, platform units, backoff reset and cap, terminate on stop, exit on a directly stopped child, the recycle exit code, the policy passed to `run`, returning on recycle. Two of them (no terminate; no return on recycle) made tests hang rather than fail, which stalled the mutation run until it was killed by hand; every test now has a 120 s limit (`pytest-timeout`).

Exploratory: `make e2e` found a real bug the in-process tests missed — run as `python -m kiln_worker`, the module is `__main__`, so a `spawn` child could not import the target function and every child crashed in a restart loop. The child's code moved to `kiln_worker/process.py`, and a test now runs the real command as a subprocess (it fails with the old layout, checked).

## Review score

| #   | Criterion | Score | Evidence |
| --- | --------- | ----- | -------- |
