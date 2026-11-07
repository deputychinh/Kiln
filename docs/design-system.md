# Design system

Single source: `packages/ui` (`@kiln/ui`). The web app uses only its tokens and components. Follows `references/frontend-and-ux.md`. The product benchmark behind the KILN-35 redesign (Frame.io, Eagle, Figma, Dropbox Replay) is `docs/delivery/KILN-35/benchmark.md`.

## Direction

A tool for artists: **the asset is the hero**, the interface steps back. Neutral zinc surfaces with no tint (so texture colours are judged correctly), dark by default, with a light theme that follows `prefers-color-scheme` until the person picks one (the theme button in the top bar, kept in `localStorage`). One accent (ember, the kiln's fire) for the primary action, selection and focus-adjacent emphasis — nothing else is coloured unless it means something (status). Dense on desktop, roomier on phones. Previews are edge to edge, 4:3, over a checkerboard so transparent pixels read as transparent.

## Tokens (`--kiln-*`, `packages/ui/src/tokens/tokens.css`)

Three tiers: primitives (`--kiln-zinc-*`, `--kiln-ember-*`, `--kiln-green-*` …) → semantic roles (`--kiln-color-*`, the only colours components use) → component CSS.

| Group     | Tokens                                                                                                                                                                                                                                                            |
| --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Surfaces  | `surface` (page), `surface-sunken` (wells, inputs), `surface-raised` (cards, panels), `surface-overlay` (menus), `surface-hover`, `surface-pressed`, `surface-selected` (accent tint)                                                                             |
| Content   | `on-surface`, `on-surface-muted`, `on-selected`, `on-primary`, `tooltip` / `on-tooltip`, `on-media` and `media-scrim` (text over previews), `scrim` (drop overlay), `checker-a/b`                                                                                 |
| Accent    | `primary`, `primary-hover`; `focus` (blue, distinct from the accent)                                                                                                                                                                                              |
| Status    | `success`, `warning`, `danger`, `info` — always with words or an icon                                                                                                                                                                                             |
| Lines     | `outline` (control borders, ≥ 3:1), `outline-variant` (hairline dividers)                                                                                                                                                                                         |
| Spacing   | 4 px scale: `--kiln-space-1` (4) … `--kiln-space-9` (64)                                                                                                                                                                                                          |
| Type      | Inter Variable (self-hosted, `@fontsource-variable/inter`); `--kiln-text-xs` 12 · `sm` 13 · `ui` 14 (controls) · `md` 16 (body) · `lg` 18 · `xl` 22 · `2xl` 28; weights regular/medium/semibold/bold; `--kiln-tracking-tight/title`; leading tight/normal         |
| Shape     | `--kiln-radius-sm/md/lg/xl/full`, `--kiln-border-hairline/focus`, `--kiln-checker-size`                                                                                                                                                                           |
| Elevation | `--kiln-shadow-1/2/3` (on dark, 2 and 3 add a hairline highlight)                                                                                                                                                                                                 |
| Motion    | `--kiln-duration-fast/base/slow/pulse`, `--kiln-delay-tooltip`, `--kiln-ease-standard/enter/exit`; durations are zero under `prefers-reduced-motion`                                                                                                              |
| Layers    | `--kiln-z-raised/header/nav/drawer/tray/dialog/tooltip/toast/overlay`                                                                                                                                                                                             |
| Sizes     | targets `--kiln-target-min` (24) / `-control` (36) / `-primary` (44); icons `--kiln-icon-sm/md/lg` (16/20/32, also `ICON_SIZE` for icon components); shell `--kiln-shell-bar/rail/sidebar/bottom-nav/inspector`, `--kiln-tray-width`, `--kiln-card-min(-compact)` |

Contrast (checked with `docs/delivery/KILN-35/contrast.md`): body and muted text ≥ 4.5:1 on every surface, status colours ≥ 4.5:1 on surface and raised, control borders and focus ≥ 3:1, in both themes.

Icons: lucide (`lucide-react`, pinned), 1.5–2 px strokes at 16/20/32 px; an icon next to a label is decorative (`aria-hidden`), an icon-only control is an `IconButton` whose label is its name and tooltip.

## Layout per window size class (Material 3)

| Class    | Width       | Navigation                                | Top bar                      | Gallery                                                            |
| -------- | ----------- | ----------------------------------------- | ---------------------------- | ------------------------------------------------------------------ |
| compact  | < 600 px    | bottom navigation bar                     | brand, Upload (icon), theme  | 2 columns; detail replaces the list                                |
| medium   | 600–839 px  | navigation rail (80 px, icon above label) | brand, search, Upload, theme | 3–4 columns; detail replaces the list                              |
| expanded | 840–1199 px | navigation rail                           | as medium                    | grid + inspector (400 px) on the right, sticky, scrolls on its own |
| large    | ≥ 1200 px   | sidebar (220 px, icon beside label)       | as medium                    | as expanded                                                        |

The grid follows the list pane's width (container query), not the viewport. Material 3 uses a bar or rail for 3–5 destinations; Kiln has one (Assets) so far, shown so the shell does not move when the next destination arrives. Uploads: the Upload button (top bar, empty state) opens the file picker; dragging files anywhere over the window shows a drop overlay (new assets, plus "new version of …" when an asset is open); running uploads live in a collapsible tray in the bottom corner (above the bottom bar on compact).

## Components

- v0.1 (KILN-6, KILN-26): `Button` (primary 44 px, secondary, ghost; leading icon; `buttonClassName` for links), `Badge` (soft tint, optional icon), `AssetThumb` (4:3, checkerboard, reports the failed URL), `Skeleton` (line, tile, card), `EmptyState` (icon, heading level), `ErrorState` (`titleAs` for a page-level error), `ProgressBar` (determinate, `role="progressbar"`).
- v0.2 (KILN-35): `IconButton` (label = name + tooltip, sizes 32/36/44, toggle state), `Tooltip` (hover after a delay or keyboard focus; hoverable; Escape dismisses — WCAG 1.4.13), `StatusDot`, `Toolbar` (start and end clusters), `SegmentedControl` (native radio group), `Tabs` (WAI-ARIA tabs, automatic activation, arrow/Home/End), `FilePickerButton` (the 2.5.7 alternative to every drop), `DropOverlay` (whole-window drop targets, pointer only). `Dropzone` was removed with the redesign.
- Next: `Dialog`, `Drawer`, `Avatar`, `CommentThread`, `AnnotationLayer`, `CompareSlider`, `TextField`; v0.3 `TagChip`, `SearchBar` (natural language → filter chips), `RuleViolation`.

Every component has a story for each state, role-based tests, and no hard-coded strings (copy comes in through props).

## Storybook

`make storybook` (port 6006) shows every component in each state with autodocs, a **Theme** toolbar (dark default, light) and the accessibility panel. Stories live next to the component (`<Name>/<Name>.stories.tsx`, CSF 3, `satisfies Meta<typeof Name>`); sample copy and images are inline (no remote URLs). `make test` fails when a component folder has no stories; `make e2e-ui` runs axe over every story in both themes (KILN-7). Publishing it is KILN-20.

## Budgets

- Accessibility: WCAG 2.2 AA; targets ≥ 24 px (2.5.8); focus not obscured (2.4.11); an alternative to every drag (2.5.7: the Upload and "Upload new version" buttons for the drop overlay, buttons for the compare slider and the 3D view).
- Performance: LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1; thumbnails have fixed dimensions to avoid layout shift; the font is self-hosted with `font-display: swap`; the 3D viewer loads lazily: three.js is only in its own chunk, and `apps/web/scripts/check-bundle-budget.mjs` fails the build when the first load passes its budget (see the script for the current numbers), the viewer route 8 kB or the scene 280 kB, or when three.js reaches the first load. The viewer's buttons and keys are the 2.5.7 alternative to orbit, pan and zoom gestures.
