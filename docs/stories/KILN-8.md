# KILN-8: Compare two versions of an asset

- Release: v0.2 · Status: doing · Owner: Claude (deliver-loop)

## Story

As an **art lead reviewing a revision**, I want to put two versions of an asset next to each other — or swipe one over the other — so that I can see what changed before I approve it.

INVEST: Independent ☑ (versions and their previews exist since KILN-4/30) · Negotiable ☑ · Valuable ☑ · Estimable ☑ · Small ☑ (web only, previews at 512 px) · Testable ☑

## Acceptance criteria

| Id                   | Given                                                                                                        | When                                      | Then                                                                                                                                                                                     |
| -------------------- | ------------------------------------------------------------------------------------------------------------ | ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1                  | an asset with two or more versions                                                                           | I choose "Compare versions" in its detail | a full-width page shows the newest version and the one before it side by side, each with its number, status, file name, size and age; the size difference is stated in words             |
| AC2                  | the compare page                                                                                             | I pick other versions in the two pickers  | the panes change and the URL (`?left=&right=`) records the pair, so reload, Back and a shared link show the same comparison                                                              |
| AC3                  | two image versions                                                                                           | I switch to Swipe                         | the right version is laid over the left and a slider (also arrow keys) reveals it from 0 to 100 %; the mode is in the URL (`mode=swipe`)                                                 |
| AC4 (edge)           | a version with no preview (processing, failed, or a model that could not render)                             | it is in a pane                           | the pane says why there is no preview instead of a broken image; Swipe is offered only when both versions have previews                                                                  |
| AC5 (negative)       | an asset with fewer than two versions, an unknown asset, or `left`/`right` naming versions that do not exist | I open the compare page                   | fewer than two: an empty state with a way back to the asset; unknown asset: not found; bad numbers: the default pair is shown and the URL is corrected (replace, no extra history entry) |
| AC6 (a11y, adaptive) | compact (< 600 px) and wide layouts, keyboard only                                                           | I compare                                 | panes stack on compact and sit side by side from 600 px; pickers are labelled selects; the slider is a labelled range input; focus starts on the page heading; axe clean                 |

## Non-functional

- Performance: no new API endpoints; the page reuses the asset's detail query (previews are already cached by their stable URLs, KILN-27).
- Security: version numbers from the URL are parsed as integers and looked up in the asset's own versions; nothing from the URL is rendered as HTML.
- Accessibility: WCAG 2.2 AA; the swipe never hides information that side-by-side shows.

## Out of scope

- Full-resolution originals, pixel diff, model compare in 3D (KILN-9), comments and approval (KILN-10/11).

## References

- `~/.claude/skills/frontend` and `css-design` skills (state in the URL, four states, labelled controls).
- WCAG 2.2: 2.5.7 Dragging Movements (the slider also works with keys), 1.3.1, 4.1.2.
- How review tools compare: side-by-side and wipe/swipe modes (e.g. Frame.io, ShotGrid/Flow review) — the reason for the two modes.

## Design

- Routes: `/assets/$assetId/compare` as `assets_.$assetId.compare.tsx` (outside the list-detail layout, full width); search params validated: `left`, `right` (positive integers), `mode` (`side` | `swipe`). The upload queue moves up to the root route so uploads survive leaving `/assets`.
- Data: `useAsset(assetId)`; `pickPair(versions, left, right)` returns the pair to show (default: newest and the one before it) and whether the URL must be corrected.
- UI: header (back to asset, h1 "Compare versions of <name>", mode toggle), two labelled `<select>`s, two panes (`AssetThumb` + facts), a size-difference line; Swipe stacks both previews and clips the top one with `clip-path: inset(0 0 0 <100-x>%)` driven by `<input type="range">`.

## QA

| AC  | Test(s)                                                                                                                                                                                                                                                                                                                         | Result |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| AC1 | `ComparePage.test.tsx` "shows the newest version against the one before it, with facts and the size change"; `AssetDetail.test.tsx` "offers Compare versions only when there are two versions or more" and "offers no comparison for an asset with one version"; `compare.util.test.ts` pickPair default; e2e `compare.spec.ts` | pass   |
| AC2 | `ComparePage.test.tsx` "records the chosen pair in the URL and shows it", "swaps the sides when a picker chooses the version the other side shows"; e2e reload keeps the comparison                                                                                                                                             | pass   |
| AC3 | `ComparePage.test.tsx` "lays the right version over the left in Swipe and reveals it with a labelled slider"; e2e arrow keys move the slider (50 → 52)                                                                                                                                                                          | pass   |
| AC4 | `ComparePage.test.tsx` "explains a missing preview and offers no Swipe without both previews"; `compare.util.test.ts` canSwipe                                                                                                                                                                                                  | pass   |
| AC5 | `ComparePage.test.tsx` "says there is nothing to compare with one version, with a way back", "corrects a URL that names versions that do not exist, without a new history entry", "says the asset was not found"; `compare.util.test.ts` parseCompareSearch and pickPair fallbacks                                              | pass   |
| AC6 | e2e `compare.spec.ts` on desktop (1280) and mobile (Pixel 7): heading focused, axe wcag2a/aa/22aa clean in both modes; labelled selects, radios and range input in the component tests                                                                                                                                          | pass   |

Gates: `make lint` 0; `make test` 694 Python + 2 + 63 + 220 web tests passed; `make e2e` 26 passed. Screenshots looked at: `apps/web/test-results/screens/compare-{side,swipe}-{desktop,mobile}.png`.

Found on the way: the KILN-27 cache e2e waited up to 61 s for a signing-window boundary under the 30 s default timeout, so it failed in the last minute of every window; its timeout is now 120 s (fixed by arithmetic — this run did not land in that minute).

## Review rounds

| Round | Score | Findings → fixes |
| ----- | ----- | ---------------- |
