# KILN-7: Storybook for the design system

- Release: v0.1 · Status: doing · Owner: Claude (deliver-loop)

## Story

As a **front-end developer (or a reviewer judging visual consistency)**, I want every `@kiln/ui` component shown in each of its states, in both themes, with an accessibility check, so that I can build screens from the design system without reading its source and spot a regression before it reaches the app.

INVEST: Independent ☑ (only `packages/ui`) · Negotiable ☑ · Valuable ☑ (ADR 0001 §8: the evidence for visual consistency) · Estimable ☑ · Small ☑ (six components; publishing it is KILN-20) · Testable ☑

## Acceptance criteria

| Id             | Given                                   | When                                   | Then                                                                                                                                                                                                                                                                                                        |
| -------------- | --------------------------------------- | -------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1            | the repo is installed                   | a developer runs `make storybook`      | Storybook starts on port 6006 with the Kiln tokens loaded; `npm run build -w @kiln/ui` (part of `make build` and CI) builds it to `packages/ui/storybook-static`                                                                                                                                            |
| AC2            | the six components                      | a developer opens Storybook            | `Button`, `Badge`, `AssetThumb`, `Skeleton`, `EmptyState` and `ErrorState` each have a story per state: every `ButtonVariant` plus disabled; every `BadgeTone`; image, no image, broken image; every `SkeletonShape`; with and without body/action; with retry, retrying, without retry, page-level heading |
| AC3            | a story is open                         | a developer switches the theme toolbar | the canvas and docs switch between the dark and light token sets (`data-theme`), defaulting to dark like the app                                                                                                                                                                                            |
| AC4            | a story                                 | the docs page is opened                | an autodocs page lists the props with the JSDoc descriptions from the component source                                                                                                                                                                                                                      |
| AC5 (guard)    | a new component folder without a story  | `make test` runs                       | the test fails, naming the folder; every story renders in the unit suite and its `play` function (where present) passes                                                                                                                                                                                     |
| AC6 (a11y)     | the built Storybook                     | `make e2e-ui` runs (and CI)            | every story is opened in both themes and axe (WCAG 2.2 AA tags) reports no serious or critical violation, colour contrast included; a story that throws or logs a console error fails the run                                                                                                               |
| AC7 (negative) | an interactive story (ErrorState retry) | its `play` runs                        | pressing **Try again** calls `onRetry` once; while retrying, pressing it again does not call it                                                                                                                                                                                                             |

## Non-functional

- Security: Storybook is a dev/build tool only (devDependencies; `npm audit --omit=dev` unaffected); the static build is not deployed in v0.1 (public Storybook is KILN-20); stories use inline SVG data URLs, no remote images; no telemetry (`core.disableTelemetry`).
- Accessibility: the addon-a11y panel runs axe in the UI; the e2e gate runs it headless (AC6).
- Performance: none for the app (Storybook is not in the app bundle); CI build time grows by one Storybook build.
- Maintainability: stories sit next to their component (`X/X.stories.tsx`); copy in stories is sample data passed through props, as in the app.

## Out of scope

- Publishing Storybook (Chromatic or Pages) and visual-regression snapshots → KILN-20 (v0.4).
- `Dropzone`, `ProgressBar` stories arrive with the components in KILN-26.
- Storybook's Vitest browser-mode addon: the jsdom `composeStories` suite plus the Playwright axe pass give the same guarantees without a second browser runner.

## References

- Storybook 10 docs — Writing stories (CSF 3), `composeStories` portable stories in Vitest, accessibility testing with addon-a11y: https://storybook.js.org/docs/writing-stories, https://storybook.js.org/docs/api/portable-stories/portable-stories-vitest, https://storybook.js.org/docs/writing-tests/accessibility-testing
- Deque axe-core rule tags (`wcag2a`, `wcag2aa`, `wcag21aa`, `wcag22aa`): https://github.com/dequelabs/axe-core/blob/develop/doc/API.md#axe-core-tags
- Brad Frost, _Atomic Design_ ch. 4 — pattern libraries document every state of a component: https://atomicdesign.bradfrost.com/chapter-4/
- `references/frontend-and-ux.md` (four states per view, tokens, WCAG 2.2 AA).

## Design

- API / data: none.
- `packages/ui/.storybook/main.ts` (`@storybook/react-vite`, addons docs + a11y, stories `src/**/*.stories.tsx`, telemetry off) and `preview.tsx` (imports `tokens.css`, a `theme` global toolbar that sets `data-theme` on `<html>`, `a11y.test = 'error'`, autodocs tag).
- Stories: `src/components/<Name>/<Name>.stories.tsx`, CSF 3 with `satisfies Meta<typeof Name>`.
- Unit guard: `src/stories.test.tsx` globs the stories with `import.meta.glob`, renders each composed story (and runs `play`), and checks that every component folder has a stories file.
- E2E: `packages/ui/e2e/storybook.spec.ts` + `playwright.config.ts`; serves `storybook-static` with `vite preview`, reads `index.json`, opens each story's `iframe.html?id=…&globals=theme:<t>` and runs `@axe-core/playwright`.
- Make: `storybook` (exists), `e2e-ui` (new); CI node job runs the Storybook e2e after the build.

## QA

| AC  | Test(s)                                                                                                                                                                               | Result |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| AC1 | `make storybook` (manual: starts on 6006); `npm run build -w @kiln/ui` in `make build` and CI → `storybook-static`                                                                    | pass   |
| AC2 | 23 stories: Button 4, Badge 5, Skeleton 2, EmptyState 3, ErrorState 4, AssetThumb 5; each rendered by `src/stories.test.tsx`                                                          | pass   |
| AC3 | `e2e/storybook.spec.ts` asserts `<html data-theme>` per theme; screenshots at 1280 px (dark docs, light story) and 390 px (thumb) checked by eye                                      | pass   |
| AC4 | autodocs page shows JSDoc prop descriptions (screenshot of ErrorState docs: `titleAs` description)                                                                                    | pass   |
| AC5 | `stories.test.tsx` "has a stories file for every component folder"; mutation: removing `Badge.stories.tsx` fails with `[ 'Badge' ]`                                                   | pass   |
| AC6 | `make e2e-ui`: 23 stories × 2 themes through axe (WCAG 2.0–2.2 A/AA tags) + console/page errors; mutations: dropping `alt` → `image-alt` failures; a throwing story → console failure | pass   |
| AC7 | `ErrorState` stories `WithRetry` / `Retrying` `play`; mutation: removing the `isRetrying` guard fails `Retrying`                                                                      | pass   |

Exploratory: docs canvas in the dark theme first showed a white frame around dark components → `.docs-story` follows the token surface; thumbs blended into the page → story decorator puts them on the card's raised surface. `npm audit`: Storybook adds one dev-only moderate chain (`react-docgen-typescript` plugin → `glob` → `minimatch`, the same advisory the ESLint chain already has); `npm audit --omit=dev` stays clean.
