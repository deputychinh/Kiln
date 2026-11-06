# ADR 0009: Hung jobs end their worker process: an in-process watchdog and a supervisor backstop

- Status: accepted · 2026-11-06

## Context

KILN-24 stops extending a hung job's lease after its 30-minute maximum runtime so another worker can retry it, but the worker running it stays blocked for good, and a stop request waits for it without a bound (KILN-25). The backlog first proposed running every job in its own child process the worker can kill. Review of a first implementation showed a second gap: native code that holds the GIL — or a frozen process (SIGSTOP, a stuck page fault) — stops every thread of the process, the in-process watchdog and the lease heartbeat included, so the lease lapses at most `lease − heartbeat` (200 s) after the freeze and another worker can claim the job while the frozen one still holds it.

## Decision

1. **No child process per job.** Spawning one per job costs a new interpreter, imports and connections on every job; the worker child (KILN-25) is already the unit the supervisor replaces.
2. **In-process watchdog** (`kiln_worker/watchdog.py`): one thread per job ends the process with `os._exit(76)` at the job's maximum runtime, or 60 s (configurable) after a stop if the job is still running. It works while the job waits in native code that releases the GIL (I/O, sockets, sleeps) and logs job, version, attempt, runtime and budget.
3. **Supervisor backstop** through a lock-free shared `JobBeacon` (`RawArray`: job start, last sign of life, job id). The watchdog thread writes a sign of life every poll. The supervisor kills a child that is in a job and showed no sign of life for 60 s (`SUPERVISOR_LIVENESS_SECONDS`, well inside the 200 s a frozen lease has left) or is still in one job 5 s past its maximum runtime, then replaces it at once (no crash backoff).
4. **Bounded shutdown and reaping**: a killed child is waited for at most 10 s (a process in uninterruptible sleep cannot die at once); the supervisor kills a child that has not exited 10 s after its stop grace, and keeps its liveness and deadline checks while it waits. The grace is capped at 120 s so liveness + grace + kill margin (190 s) stays inside the 200 s a frozen lease has left.

## Consequences

- A job never runs in two processes at once through a hang or a freeze, during work or during a stop; a test pins every deadline against the lease and heartbeat constants. The claim itself is shown in the beacon, so a freeze around it is seen too. Known gap (KILN-33): a lease heartbeat that fails or is lost while the process stays alive does not end the job.
- The watchdog's exit and the supervisor's kill drop the database connection (rolled back), and the model sandbox child exits with its parent; thumbnails are written in one PUT; retries and burial use the existing lease and attempts path.
- A lock-free beacon cannot deadlock the supervisor when a child dies mid-write; the job id in it is for logs only.
- Deployments must give the worker a stop timeout of at least grace + 10 s (70 s by default).
- Exit code 76 means "a job overran"; 75 (KILN-25) means "recycle".
