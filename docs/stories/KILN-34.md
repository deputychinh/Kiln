# KILN-34: One poll per processing asset

- Release: v0.2 · Status: doing · Owner: Claude (deliver-loop)

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

| Round | Score | Findings → fixes                                                                                                                                                                                                                                                                                                                                                                       |
| ----- | ----- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1     | 8.0   | The queue's fetch stored answers without the detail's `keepSignedUrls` (two definitions of one query); cancelling waited for the shared request and could end Ready; no tests for AC3, URL retention, cancel mid-fetch or errors; deprecated `fetchQuery` → one `assetDetailQueryOptions` for both hooks, `untilAborted` race, `queryClient.query`, four tests each killing its mutant |
