# KILN-30: Upload a new version from the asset detail

- Release: v0.2 · Status: doing · Owner: Claude (deliver-loop)
- Picked before the debt items KILN-29 and KILN-31 to 33 because it is the next thing an artist can see and use (ruling, 2026-11-07).

## Story

As an **artist**, I want to drop a revised file on an asset's detail pane, so that the asset keeps one history of versions instead of a new asset per revision.

INVEST: Independent ☑ (the API exists: `POST /api/v1/assets/{id}/versions`) · Negotiable ☑ · Valuable ☑ · Estimable ☑ · Small ☑ (web only) · Testable ☑

## Acceptance criteria

| Id             | Given                              | When                                                            | Then                                                                                                                                                                                                           |
| -------------- | ---------------------------------- | --------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1            | an asset's detail pane             | I drop or choose a file of the asset's kind                     | it uploads with progress as the asset's next version, the versions list shows it at once, and when processing ends it is Ready and becomes the asset's preview in the detail and the gallery, without a reload |
| AC2 (negative) | an image asset (or a model asset)  | I add a file of the other kind                                  | it is refused before anything is sent, with a message naming the kind the asset takes; if the API refuses a version for its kind (`ASSET_KIND_MISMATCH`), the same message shows and Retry is not offered      |
| AC3 (negative) | the detail pane                    | I add an unsupported, empty, oversized or over-long-named file  | it is refused before sending with the same messages as gallery uploads                                                                                                                                         |
| AC4 (edge)     | several files dropped on one asset | they upload                                                     | they become versions in the order dropped (one at a time per asset); uploads to other assets and new assets still run two at a time                                                                            |
| AC5 (edge)     | a version upload running           | I open another asset, go back to the list, or cancel / retry it | the upload keeps running (it belongs to the page, not the pane); Cancel stops it; Retry reuses its idempotency key, so a lost reply never makes two versions                                                   |
| AC6 (a11y)     | compact and expanded layouts       | I use only the keyboard or a screen reader                      | the version zone is named after the asset, its button reaches the file picker, and each outcome is announced once                                                                                              |

## Non-functional

- Security: the API stays the gate (kind, type, size; magic bytes in the worker); the browser check is feedback only. File names are rendered as text.
- Accessibility: WCAG 2.2 AA; axe clean in e2e at 390 and 1280 px.
- Performance: no extra requests while idle; the detail refreshes once when the version is created and polls only while it processes.

## Out of scope

- Comparing versions (KILN-8), deleting versions, choosing which version is the cover.

## References

- `~/.claude/skills/init-project/references/frontend-and-ux.md` (Material 3 list-detail, four states).
- WCAG 2.2: 2.5.7 Dragging Movements (button alternative), 4.1.3 Status Messages.
- Idempotency: IETF `draft-ietf-httpapi-idempotency-key-header` (ADR 0006).

## Design

- API: unchanged (`POST /api/v1/assets/{id}/versions` with `UploadDeclaration`; 422 `ASSET_KIND_MISMATCH`).
- Web: one upload queue for the whole `/assets` page (`UploadsProvider` in the layout) shared by the gallery panel and the detail's version panel; a row has an optional target asset; the scheduler starts at most two rows and never two for the same asset. `declareUpload(file, kind)` refuses the other kind (`not_an_image` / `not_a_model`). A created version refreshes that asset's detail; a ready one refreshes the detail and the gallery.
- UI: in the detail, an "Add a version" zone below the facts with only that kind in the picker; its rows and announcements are its own; same zone in every size class.

## QA

| AC  | Test(s) | Result |
| --- | ------- | ------ |

## Review rounds

| Round | Score | Findings → fixes |
| ----- | ----- | ---------------- |
