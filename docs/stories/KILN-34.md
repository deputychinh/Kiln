# KILN-34: One poll per processing asset

- Release: v0.2 · Status: done · Owner: Claude (deliver-loop)

## Story

As a **user watching a new version process**, I want the page to ask the server once per interval, not twice, so that open details and running uploads do not double the load while a preview is made.

## Acceptance criteria

| Id         | Given                                                                              | When                                | Then                                                                                                                    |
| ---------- | ---------------------------------------------------------------------------------- | ----------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| AC1        | a version uploading from the queue and its asset's detail open (polling every 3 s) | the queue checks for the preview    | it reads the detail's cached answer when that answer is younger than the poll interval, and sends no request of its own |
| AC2        | the same upload with the detail closed                                             | the queue checks                    | it fetches as before, and the answer lands in the shared cache, so opening the detail shows it at once                  |
| AC3 (edge) | a fetch in flight from the detail                                                  | the queue checks at the same moment | the two share the one request (deduplicated)                                                                            |

## Design

`waitForPreview` calls `queryClient.query({ ...assetDetailQueryOptions(id), staleTime: PROCESSING_POLL_MS })`, raced against the upload's signal, instead of `getAsset`; `useAsset` spreads the same `assetDetailQueryOptions`, so either side's fetch keeps still-valid signed URLs and never a failed one (failed previews live in a per-asset registry): fresh cache → no request; stale → one request shared with any in-flight one. Stable signed URLs (KILN-27) keep previews equal across both readers.

## QA

| AC  | Test(s)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | Result |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| AC1 | `useUploads.test.tsx` "reads a fresh detail answer from the cache instead of polling the API again" (mutation: `staleTime: 0` → fails)                                                                                                                                                                                                                                                                                                                                                                              | pass   |
| AC2 | `useUploads.test.tsx` "fetches when nothing fresh is cached and leaves the answer in the shared cache"; existing "creates, sends, completes and waits for the preview"; "keeps a still-valid preview URL when its own fetch brings a newly signed one" (mutant: queue without the shared structuralSharing → fails); "retries after a failed shared fetch and keeps the cached detail meanwhile"; "ends a row as cancelled at once even while a shared detail request is in flight" (mutant: no abort race → fails) | pass   |
| AC3 | `useUploads.test.tsx` "shares a detail request already in flight instead of sending another"                                                                                                                                                                                                                                                                                                                                                                                                                        | pass   |

Gates after round 1: `make lint` 0; `make test` green (231 web tests); `make e2e` green.

## Review rounds

| Round | Score | Findings → fixes                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| ----- | ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1     | 8.0   | The queue's fetch stored answers without the detail's `keepSignedUrls` (two definitions of one query); cancelling waited for the shared request and could end Ready; no tests for AC3, URL retention, cancel mid-fetch or errors; deprecated `fetchQuery` → one `assetDetailQueryOptions` for both hooks, `untilAborted` race, `queryClient.query`, four tests each killing its mutant                                                                                                    |
| 2     | 9.5   | Same reviewer: mutants A (staleTime 0), B (no shared structuralSharing), C (no abort race) and E (failed registry ignored) killed; D (rethrow instead of polling again) survived because the client's two retries absorbed the test's single failure → the test now fails every attempt of the first poll and kills D. Left (minor): a hand-typed `AssetDetailQuery` instead of `queryOptions()`, and the failed-preview registry is never cleared on sign-out (no sign-in yet, KILN-12). |

## Score

Round 2 (the round-1 reviewer, resumed):

| #   | Criterion             | Score   |
| --- | --------------------- | ------- |
| 1   | Requirements fit      | 1       |
| 2   | Test depth            | 0.5     |
| 3   | Reliability           | 1       |
| 4   | Security              | 1       |
| 5   | Maintainability       | 1       |
| 6   | UX                    | 1       |
| 7   | Accessibility         | 1       |
| 8   | Performance           | 1       |
| 9   | Docs and traceability | 1       |
| 10  | Delivery              | 1       |
|     | **Total**             | **9.5** |

Test depth was 0.5 for the surviving mutant D, fixed in the ship commit.
