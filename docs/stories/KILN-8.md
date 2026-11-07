# KILN-8: Compare two versions of an asset

- Release: v0.2 · Status: done · Owner: Claude (deliver-loop)

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

| AC  | Test(s)                                                                                                                                                                                                                                                                                                                                                                             | Result |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| AC1 | `ComparePage.test.tsx` "shows the newest version against the one before it, with facts and the size change"; `AssetDetail.test.tsx` "offers Compare versions only when there are two versions or more" and "offers no comparison for an asset with one version"; `compare.util.test.ts` pickPair default; e2e `compare.spec.ts`                                                     | pass   |
| AC2 | `ComparePage.test.tsx` "records the chosen pair in the URL and shows it", "swaps the sides when a picker chooses the version the other side shows"; e2e reload keeps the comparison; "brings back the previous pair with the browser Back"; the swap test uses a non-adjacent pair (1 and 3)                                                                                        | pass   |
| AC3 | `ComparePage.test.tsx` "splits Swipe with a divider the labelled slider moves, keeping both versions’ facts"; e2e: arrow keys move the divider (50 → 52) and the right version is clipped from the left edge (`clip-path: inset(0px 0px 0px 52%)`)                                                                                                                                  | pass   |
| AC4 | `ComparePage.test.tsx` "explains a missing preview and offers no Swipe without both previews"; `compare.util.test.ts` canSwipe                                                                                                                                                                                                                                                      | pass   |
| AC5 | `ComparePage.test.tsx` "says there is nothing to compare with one version, with a way back", "corrects a URL that names versions that do not exist, without a new history entry", "says the asset was not found"; `compare.util.test.ts` parseCompareSearch and pickPair fallbacks; "drops an unknown mode from the URL in place"; `compare.util.test.ts` rejects a 10-digit number | pass   |
| AC6 | e2e `compare.spec.ts` on desktop (1280) and mobile (Pixel 7): heading focused, axe wcag2a/aa/22aa clean in both modes; labelled selects, radios and range input in the component tests; "keeps the upload queue on this page: uploads belong to the app, not the assets page"                                                                                                       | pass   |

Gates after the round-1 fixes: `make lint` 0; `make test` 694 Python + 2 + 63 + 224 web tests passed; `make e2e` 26 passed. Screenshots looked at: `apps/web/test-results/screens/compare-{side,swipe}-{desktop,mobile}.png`.

Found on the way: the KILN-27 cache e2e waited up to 61 s for a signing-window boundary under the 30 s default timeout, so it failed in the last minute of every window; its timeout is now 120 s (fixed by arithmetic — this run did not land in that minute).

## Review rounds

| Round | Score | Findings → fixes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ----- | ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1     | 8.5   | Swipe was reversed (the right picker's version on the left half) and hid each version's facts, breaking the story's own rule; the swap test could not fail (adjacent pair); no test for Back, the digit limit or the app-wide upload queue (two mutants survived); swipe images did not refresh expired URLs; `?mode=diff` stayed in the URL → the right version is clipped at a divider with side labels, both captions stay under the stage, `onError` refreshes previews, an unknown mode is detected by value (TanStack Router merges raw params into the validated search) and removed in place; `VersionPane` and `SwipeStage` split out under the 300-line limit; tests for each gap kill the mutants. |
| 2     | 9.5   | Same reviewer with two different images: the divider at 20 % shows v2 on the left fifth and v3 on the rest; captions stay; `?mode=diff` variants corrected; keyboard-only swipe; axe clean at 1280, 390 and dark. Mutants M3, M5, M6, M8 and the reverted clip killed; the only survivor (swipe `onError` dropped) is now killed by "fetches fresh preview URLs when a swiped preview fails to load". Left open (minor): `mode=swipe` kept in the URL while a failed version forces Side; unknown extra params kept.                                                                                                                                                                                          |

## Score

Round 2 (the round-1 reviewer, resumed):

| #   | Criterion             | Score   |
| --- | --------------------- | ------- |
| 1   | Requirements fit      | 1       |
| 2   | Test depth            | 1       |
| 3   | Reliability           | 1       |
| 4   | Security              | 1       |
| 5   | Maintainability       | 1       |
| 6   | UX                    | 1       |
| 7   | Accessibility         | 1       |
| 8   | Performance           | 1       |
| 9   | Docs and traceability | 0.5     |
| 10  | Delivery              | 1       |
|     | **Total**             | **9.5** |
