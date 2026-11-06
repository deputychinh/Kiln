# KILN-26: Upload from the browser

- Release: v0.1 · Status: doing · Owner: Claude (deliver-loop)

## Story

As an **artist**, I want to drop image and `.glb` files onto the gallery (or pick them with a button) and watch each one upload and get its preview, so that I can add work without the CLI or the API.

INVEST: Independent ☑ (uses the KILN-2/3/21 API as is) · Negotiable ☑ · Valuable ☑ (closes phase 1: "e2e upload → thumbnail visible") · Estimable ☑ · Small ☑ (new assets only; new versions of an existing asset are KILN-30) · Testable ☑

## Acceptance criteria

| Id             | Given                                                        | When                                                                     | Then                                                                                                                                                                                                                                                                               |
| -------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1            | the gallery (any state except the first load)                | a person drops files on the dropzone or picks them with **Choose files** | each file becomes a row in an upload list with its name, a progress bar and its state; the button is the keyboard and touch alternative to dragging (WCAG 2.5.7)                                                                                                                   |
| AC2            | a supported file (PNG, JPEG, WebP, `.glb`; 1 byte – 500 MiB) | it uploads                                                               | the app creates the asset (`POST /api/v1/assets` with an `Idempotency-Key`), sends the file to the signed form with progress in %, then completes it; the row reads Uploading n % → Processing preview → Ready                                                                     |
| AC3            | an upload completed                                          | the worker finishes the preview                                          | the gallery refreshes and the new card shows its preview without a reload (the row polls the asset every 3 s for at most 5 minutes); a failed preview shows the failure reason on the row                                                                                          |
| AC4 (negative) | an unsupported type, an empty file or one over 500 MiB       | it is added                                                              | the row fails at once with the reason ("Only PNG, JPEG, WebP and .glb files", "This file is empty", "Larger than 500 MB") and nothing is sent                                                                                                                                      |
| AC5 (negative) | the API, storage or network fails at any step                | the upload runs                                                          | the row says what failed and offers **Retry**, which reuses the same idempotency key (no duplicate asset) and gets a fresh signed form; **Remove** clears the row                                                                                                                  |
| AC6            | an upload is running                                         | the person presses **Cancel**                                            | the transfer stops, the row reads Cancelled and can be retried or removed; nothing else in the list stops                                                                                                                                                                          |
| AC7            | many files at once                                           | they are added                                                           | at most 2 upload at a time, the rest wait as Queued; the list shows the count of finished/total                                                                                                                                                                                    |
| AC8 (a11y)     | keyboard only or a screen reader, any size class, any theme  | the person uploads                                                       | Choose files, Cancel, Retry and Remove are reachable buttons with names that include the file name; progress bars have accessible names and values; a polite live region announces each file's end state once; axe finds no serious/critical issue with a running and a failed row |

## Non-functional

- Security: the browser sends the file only to the signed POST form the API issued (the policy pins key, type and exact size, ADR 0004); the API stays the gate for type and size and the worker checks magic bytes; file names are untrusted and rendered as text; no secrets in the browser. The bucket must allow CORS only from the app origin in deployed environments (SeaweedFS reflects any origin locally) — recorded in `docs/security.md`.
- Reliability: idempotency keys make retries safe; uploads are cancellable with `AbortController`/`XMLHttpRequest.abort`; polling is bounded; leaving the page abandons pending uploads, which maintenance expires after 24 h (KILN-22).
- Performance: files are streamed by the browser (no reading into memory); 2 concurrent uploads; the gallery refetches once per finished file, not per progress event.
- UX: Nielsen #1 (visibility of status: % and state per file), #9 (errors say what to do), #3 (cancel); Material 3 progress indicators (linear, determinate).

## Out of scope

- A new version of an existing asset from the detail pane → **KILN-30** (v0.2).
- Resumable/multipart uploads for very large files (500 MiB cap is the v0.1 limit).
- Uploads that survive a page reload.

## References

- MDN — `XMLHttpRequest.upload` progress events (fetch has no upload progress): https://developer.mozilla.org/en-US/docs/Web/API/XMLHttpRequest/upload ; HTML drag and drop with file input fallback: https://developer.mozilla.org/en-US/docs/Web/API/HTML_Drag_and_Drop_API/File_drag_and_drop
- AWS S3 — browser-based uploads with POST policies: https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-UsingHTTPPOST.html
- WCAG 2.2 SC 2.5.7 Dragging Movements; ARIA `progressbar` role: https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements.html , https://www.w3.org/TR/wai-aria-1.2/#progressbar
- Material Design 3 — progress indicators: https://m3.material.io/components/progress-indicators/overview
- IETF draft `Idempotency-Key` header (KILN-21) and `references/api-design.md`.

## Design

- API / data: none (existing endpoints). Client: `apiPost` beside `apiGet` (same `ApiError` mapping).
- UI package: `Dropzone` (label, hint, button label, `accept`, `multiple`, `onFiles`; drag-over state; hidden native input driven by a `Button`), `ProgressBar` (`role="progressbar"`, value 0–100, accessible name); stories and tests for both.
- Web: `features/uploads/{utils,services,hooks,components}`:
  - `upload-file.util.ts` — declaration from a `File` (content type from `file.type`, or from the extension for `.glb`, which browsers report as empty; name = file name without extension, cut to 120 characters) or a validation error.
  - `uploads.service.ts` — `createAsset` (with `Idempotency-Key`), `sendToStorage` (XHR with progress and abort), `completeUpload`.
  - `useUploads` — the queue: statuses `queued → creating → uploading → completing → processing → ready | failed | cancelled`, concurrency 2, retry/cancel/remove, polls `getAsset` while processing (3 s, 5 min), invalidates the gallery list on completion and on ready.
  - `UploadPanel` in the gallery (all states except loading and its error): Dropzone, the list of rows, a live region.
- Copy in `locales/{en,vi}.ts`; enum `UploadStatus` in `enums/upload-status.enum.ts`; limits in `constants/upload.constant.ts`.
- UI per size class: compact — the dropzone is a full-width strip, rows stack name above bar; medium/expanded — the panel sits above the grid in the list pane, rows are one line (name, bar, state, actions).
