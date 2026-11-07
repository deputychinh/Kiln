# ADR 0010: The frozen-lease bound counts the extension, and database sockets give up on dead links

- Status: accepted · 2026-11-07 · Amends ADR 0009

## Context

ADR 0009 says a frozen worker's lease lapses at most `lease − heartbeat` (200 s) after the freeze, and caps the stop grace at 120 s so liveness + grace + kill margin (190 s) stays inside it. The KILN-28 final review showed both are off: the heartbeat waits its interval after an extension _returns_, and an extension can take a connect (5 s) plus a statement (15 s) — or, on a link that died without FIN or RST, block with no bound at all. A job's own database read on such a link blocks the heartbeat too, so the lease could lapse while the process lived.

## Decision

1. The bound is `lease − heartbeat − slowest extension`, where the slowest extension is the connect timeout plus the longer of the statement timeout and the TCP user timeout: 300 − 100 − 35 = **165 s**. The supervisor's liveness backstop (60 s + polls) stays well inside it; the invariant test asserts the arithmetic.
2. Every Postgres connection (API and worker) sets libpq `keepalives` (idle 10 s, interval 5 s, count 3) and `tcp_user_timeout` 30 s, so a dead link fails the session in about 30 s instead of blocking it.
3. The 120 s grace cap stays, but only to bound how long a shutdown can take: the stop wait keeps the liveness check, so a frozen stopping child is killed on lost liveness whatever the grace.

## Consequences

- A session on a dead link now errors after about 30 s; the heartbeat logs it and retries at its next tick, and the job's own read fails and is retried like any database error.
- Still open (KILN-33): ending the job when its heartbeat keeps failing while the process lives, a suspended host or container, and an end-to-end `python -m kiln_worker` hang test.
