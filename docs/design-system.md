# Design system

Single source: `packages/ui` (`@kiln/ui`). The web app uses only its tokens and components. Follows `references/frontend-and-ux.md`.

## Direction

A tool for artists: **the asset is the hero**, the interface steps back. Neutral dark surfaces by default (no tint, so texture colours are judged correctly), with a light theme. Dense on desktop, roomier on phones.

## Tokens (`--kiln-*`)

| Group   | Examples                                                                                                                                                          |
| ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Colour  | `--kiln-color-surface`, `-surface-raised`, `-on-surface`, `-on-surface-muted`, `-primary`, `-on-primary`, `-outline`, `-success`, `-warning`, `-danger`, `-focus` |
| Spacing | 4 px scale: `--kiln-space-1` (4) … `--kiln-space-8` (48)                                                                                                          |
| Type    | `--kiln-font-sans`, `--kiln-font-mono`; sizes `--kiln-text-xs` … `--kiln-text-2xl`; weights; leading                                                              |
| Radius  | `--kiln-radius-sm/md/lg/full`                                                                                                                                     |
| Shadow  | `--kiln-shadow-1/2`                                                                                                                                               |
| Motion  | `--kiln-duration-fast/base`, `--kiln-ease-standard`; zero under `prefers-reduced-motion`                                                                          |
| Layers  | `--kiln-z-header/drawer/dialog/toast`                                                                                                                             |
| Targets | `--kiln-target-min` (24 px), `--kiln-target-primary` (44 px)                                                                                                      |

Contrast: body text ≥ 4.5:1, large text and control borders ≥ 3:1, in both themes.

## Layout per window size class (Material 3)

| Class    | Width      | Navigation       | Gallery                                                      |
| -------- | ---------- | ---------------- | ------------------------------------------------------------ |
| compact  | < 600 px   | bottom bar¹      | 2 columns; detail replaces the list                          |
| medium   | 600–839 px | navigation rail¹ | 3–4 columns; detail replaces the list                        |
| expanded | ≥ 840 px   | expanded rail¹   | grid + detail pane on the right (sticky, scrolls on its own) |

¹ From the second destination (v0.2). Material 3 uses a bar or rail for 3–5 destinations; v0.1 has only Assets. The grid follows the list pane's width (container query), not the viewport.

## Components (build order)

- v0.1: done: `Button`, `Badge`, `AssetThumb`, `Skeleton`, `EmptyState`, `ErrorState` (KILN-6); next: `Dropzone`, `ProgressBar` (KILN-26). `IconButton`, `TextField` and `AppShell` navigation move to v0.2 with the second destination.
- v0.2: `Tabs`, `Dialog`, `Drawer`, `Avatar`, `CommentThread`, `AnnotationLayer`, `CompareSlider`, `StatusPill`.
- v0.3: `TagChip` (suggested/accepted), `SearchBar` (natural language → filter chips), `RuleViolation`.

Every component has a story for each state, role-based tests, and no hard-coded strings (copy comes in through props).

## Budgets

- Accessibility: WCAG 2.2 AA; targets ≥ 24 px (2.5.8); focus not obscured (2.4.11); an alternative to every drag (2.5.7: a file button beside the dropzone, buttons for the compare slider).
- Performance: LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1; thumbnails have fixed dimensions to avoid layout shift; the 3D viewer loads lazily.
