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

`waitForPreview` calls `queryClient.fetchQuery({ queryKey: assetDetailQueryKey(id), queryFn, staleTime: PROCESSING_POLL_MS })` instead of `getAsset`: fresh cache → no request; stale → one request shared with any in-flight one. Stable signed URLs (KILN-27) keep previews equal across both readers.

## QA

| AC  | Test(s)                                                                                                                                                                | Result    |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| AC1 | `useUploads.test.tsx` "reads a fresh detail answer from the cache instead of polling the API again" (mutation: `staleTime: 0` → fails)                                 | pass      |
| AC2 | `useUploads.test.tsx` "fetches when nothing fresh is cached and leaves the answer in the shared cache"; existing "creates, sends, completes and waits for the preview" | pass      |
| AC3 | TanStack Query deduplicates `fetchQuery` with an in-flight fetch of the same key (library behaviour, not re-tested here)                                               | by design |

Gates: `make lint` 0; `make test` all green (227 web tests); `make e2e` green.

## Review rounds

| Round | Score | Findings → fixes |
| ----- | ----- | ---------------- |
