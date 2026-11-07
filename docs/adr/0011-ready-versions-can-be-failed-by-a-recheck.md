# ADR 0011: A ready version can be failed by a re-check under stricter rules

- Status: accepted · 2026-11-07

## Context

`ready` was a final state. The worker's model rules have grown since KILN-5: every accessor bounded by its bufferView (KILN-9) and a strict node tree in every scene, not only the default one (KILN-36). Versions made ready before a rule existed still offer a 3D view the browser refuses, or a file that makes it allocate gigabytes, and nothing could take them back.

## Decision

1. The life cycle allows `ready → failed`, and only a re-check writes it: `make recheck-models` (`python -m kiln_worker.recheck`) reads every ready model version again with the worker's current sandboxed reader and renderer and fails one it now refuses with `UNREADABLE_MODEL` or `MODEL_TOO_LARGE`.
2. The write is a compare-and-set on `status = 'ready'` (as every queue write is), in one transaction with the cover change: if the version was the cover, the newest other ready version of the asset becomes the cover, or none.
3. It is a command run once per rule change (and safe to repeat), not a scheduled job: a version that could not be judged (its file changed or vanished, the preview process crashed) stays ready and is counted as skipped; storage going away stops the run with exit 1.

## Consequences

- An asset can lose its cover or a version it showed as ready; clients already handle failed versions and assets without a cover.
- The thumbnail of a failed version stays in storage until a later cleanup; nothing links to it once the cover moves.
- New model rules should come with a run of `make recheck-models` in their release notes.
