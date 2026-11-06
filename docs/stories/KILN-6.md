# KILN-6: Gallery and asset detail

- Release: v0.1 · Status: doing · Owner: Claude (deliver-loop)

## Story

As a **lead reviewing a studio's work**, I want to scan every asset as a grid of previews and open one to see its versions and their processing state, so that I can find what changed and spot failed uploads without downloading files.

INVEST: Independent ☑ (reads the KILN-2/3/4 API only) · Negotiable ☑ · Valuable ☑ (first screen a person uses) · Estimable ☑ · Small ☑ (read-only; uploading from the browser is KILN-26) · Testable ☑

## Acceptance criteria

| Id              | Given                                                                                 | When                             | Then                                                                                                                                                                                                                   |
| --------------- | ------------------------------------------------------------------------------------- | -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1             | assets exist                                                                          | a person opens `/` or `/assets`  | `/` redirects to `/assets`; the gallery lists assets newest first as cards with a preview, the name, the kind (text, not colour alone) and when it was updated (relative, absolute on hover)                           |
| AC2             | the first request is in flight                                                        | the gallery renders              | a skeleton grid with fixed-size tiles is shown and announced once ("Loading assets…"); no layout shift when cards arrive                                                                                               |
| AC3             | no assets                                                                             | the gallery loads                | an empty state says there is nothing yet and how to add the first asset (CLI/API until browser upload lands)                                                                                                           |
| AC4 (negative)  | the API is down or answers with a problem                                             | the gallery or detail loads      | an error state names what failed (the problem `title`, or "cannot reach the API") and offers **Try again**, which refetches                                                                                            |
| AC5             | more assets than one page (24)                                                        | the person presses **Load more** | the next page is fetched with `next_cursor` and appended; the button shows progress, disappears when `next_cursor` is null, and an error while loading more keeps the loaded cards and offers retry                    |
| AC6             | an asset has no ready preview (model, or still processing) or its image fails to load | its card renders                 | a same-size placeholder shows the kind; a failed image triggers one refetch of fresh signed URLs (they expire after 15 min), never a loop                                                                              |
| AC7             | a person selects a card                                                               | `/assets/<id>` opens             | the detail shows the preview, name, kind, dates and every version by number with status as a text badge, file name, size (`Intl`), and a readable failure reason when failed; the selection lives in the URL           |
| AC8             | a version is `processing`                                                             | the detail is open               | it refreshes every 3 s until no version is processing (at most 100 polls), so the status and preview appear without a reload                                                                                           |
| AC9 (negative)  | the id is unknown or not a UUID                                                       | `/assets/<id>` opens             | a "not found" state with a link back to the gallery; no retry loop on 404/422                                                                                                                                          |
| AC10 (adaptive) | window width                                                                          | the gallery or detail is shown   | compact (< 600) and medium (600–839): one pane, 2 / 3–4 columns, detail replaces the list with a back link; expanded (≥ 840): list–detail with the grid left and the detail pane right, the card marked `aria-current` |
| AC11 (a11y)     | keyboard only, any theme                                                              | the person tabs through          | every card and button is reachable in order, focus is visible, targets ≥ 24 px (primary 44 px), axe finds no serious/critical issue on the gallery and the detail                                                      |

## Non-functional

- Security: the page renders API strings as text only (React escaping, no `dangerouslySetInnerHTML`); asset names are untrusted (A03); ids from the URL are passed through `encodeURIComponent`; thumbnails come from signed URLs the API issued (no URL built in the browser); no new secrets; CSP unaffected.
- Accessibility: WCAG 2.2 AA; status by text + colour; images have `alt` = asset name; one `role="status"` for loading; focus is not obscured by the sticky header (2.4.11, `scroll-padding-top`).
- Performance: thumbnails `loading="lazy"`, `decoding="async"`, fixed `width`/`height` + `aspect-ratio` (CLS ≈ 0); route code-split; the list query is fresh for 5 min so signed URLs (and therefore image cache keys) do not change on every focus; pages of 24.
- Reliability: no retries on 4xx; 2 retries with backoff on network/5xx (TanStack default capped); polling is bounded.

## Out of scope

- Uploading from the browser (Dropzone, progress, completion) → **KILN-26** (added to v0.1; the phase-1 e2e "upload → thumbnail visible" lands there).
- Navigation bar / rail: Material 3 uses them for 3–5 destinations; v0.1 has one destination (Assets), so the bar arrives with the second destination (review queue, v0.2).
- Filters, search (KILN-15), versions compare (KILN-8), 3D viewer (KILN-9).
- Stable signed thumbnail URLs for browser caching → **KILN-27** (debt).

## References

- Material Design 3 — canonical list-detail layout and window size classes: https://m3.material.io/foundations/layout/canonical-layouts/list-detail, https://m3.material.io/foundations/layout/applying-layout/window-size-classes
- TanStack Query — infinite queries with cursors: https://tanstack.com/query/latest/docs/framework/react/guides/infinite-queries
- web.dev — optimise CLS (explicit image dimensions) and lazy-loading images: https://web.dev/articles/optimize-cls, https://web.dev/articles/browser-level-image-lazy-loading
- Nielsen Norman Group — "Load more" vs infinite scroll (keeps the footer and keyboard reachable): https://www.nngroup.com/articles/infinite-scrolling-tips/
- `references/frontend-and-ux.md` (four states, size classes, CWV), WCAG 2.2 (2.4.11, 2.5.8).

## Design

- API: unchanged (`GET /api/v1/assets?cursor&limit`, `GET /api/v1/assets/{id}`); types from `kiln.schema.ts`.
- Data: none.
- Web: `src/api/client.ts` (`apiGet` → typed JSON or an `ApiError` built from RFC 9457 problem details), `features/assets/{services,hooks,components}`; routes `/` (redirect), `/assets` (layout: gallery + outlet), `/assets/` (detail placeholder, expanded only), `/assets/$assetId`.
- UI package: `Badge`, `AssetThumb`, `Skeleton`, `EmptyState`, `ErrorState` (copy through props).
- UI (compact / medium / expanded): see AC10; the list pane is a CSS container so the grid column count follows the pane width (`auto-fill, minmax(160px, 1fr)`), not the viewport.

## QA

| AC   | Test(s)                                                                                                                                                                                                                                                                        | Result |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------ |
| AC1  | `AssetGallery.test.tsx` "redirects / to /assets", "announces loading once, then shows a card per asset"; `format.util.test.ts` (relative + absolute); `e2e/gallery.spec.ts` journey + `smoke.spec.ts`                                                                          | pass   |
| AC2  | `AssetGallery.test.tsx` "announces loading once…" (`role="status"`, "Loading assets…"); `Skeleton.test.tsx`; `AssetThumb.test.tsx` (fixed 512×512 intrinsic size)                                                                                                              | pass   |
| AC3  | `AssetGallery.test.tsx` "says what to do when there are no assets"; `e2e/gallery.spec.ts` "an empty studio sees what to do first"                                                                                                                                              | pass   |
| AC4  | `AssetGallery.test.tsx` "shows the problem title with a retry", "explains an unreachable API"; `AssetDetail.test.tsx` "offers a retry…"; `client.test.ts`; `query-client.test.ts`; `e2e/gallery.spec.ts` "a failing API shows the problem and recovers on retry"               | pass   |
| AC5  | `AssetGallery.test.tsx` "loads the next page with the cursor and appends it", "keeps the loaded cards when the next page fails, and retries it", "ignores presses on Load more while the next page is loading"                                                                 | pass   |
| AC6  | `AssetGallery.test.tsx` "shows the preview image … or a kind placeholder", "refetches signed URLs once when previews fail"; `AssetDetail.test.tsx` "shows the kind placeholder"; `AssetThumb.test.tsx`; `useThrottledCallback.test.ts`                                         | pass   |
| AC7  | `AssetDetail.test.tsx` "shows the facts and the versions newest first with text statuses"; `e2e/gallery.spec.ts` journey (opens the card, "Version 1", "Ready", preview)                                                                                                       | pass   |
| AC8  | `AssetDetail.test.tsx` "refreshes while a version is processing until it is ready"; `asset.util.test.ts` (poll bound 100)                                                                                                                                                      | pass   |
| AC9  | `AssetDetail.test.tsx` "shows \"not found\" without retrying on 404 / 422"; `e2e/gallery.spec.ts` "an unknown asset link shows \"not found\" with a way back"                                                                                                                  | pass   |
| AC10 | `ListDetail.test.tsx`; `AssetDetail.test.tsx` "moves focus to the heading … (compact)", "keeps focus in place and marks the selected card when expanded"; `useMediaQuery.test.ts`; `e2e/gallery.spec.ts` journey on desktop (aria-current) and mobile (list hidden, back link) | pass   |
| AC11 | `e2e/gallery.spec.ts` axe serious/critical = 0 on gallery, detail, empty and error (desktop + mobile); "the gallery can be used with the keyboard alone"; badge contrast ≥ 4.5:1 in both themes (computed)                                                                     | pass   |

Gates: `make ci` green (Python 368 passed, 99.86 %; ui 15 tests; web 65 tests, 97.6 % lines; build 105 kB gz first route); `make e2e` 12 passed (desktop + mobile) against the production build, real API, SeaweedFS and worker.

Mutation checks (each reverted after): 10 of 10 killed — retry boundary for 5xx, poll bound, 422 as not found, throttle boundary, Load-more guard, thumbnail refresh throttle, compact-only focus move, version order, abort passthrough, cursor paging.

Exploratory: screenshots at 412 px (Pixel 7) and 1280 px looked at — two columns on mobile, list-detail on desktop, previews from the worker; found and fixed "126 byte" → "126 bytes" and a hidden "All assets" link in the not-found state on wide screens (the e2e caught it). Not done: Lighthouse run (KILN-19), screen-reader pass (KILN-19).

## Review score

| #   | Criterion | Score | Evidence |
| --- | --------- | ----- | -------- |
