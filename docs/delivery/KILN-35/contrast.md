# KILN-35 contrast table

WCAG 2.2 contrast ratios of the semantic colour pairs in `packages/ui/src/tokens/tokens.css`, computed from the primitive hex values with the WCAG relative-luminance formula (not rounded up). Text pairs need 4.5:1, control boundaries and focus 3:1 (1.4.3, 1.4.11). Storybook's axe pass (`make e2e-ui`) and the app's axe checks (`make e2e`) confirm the rendered pairs, including the tinted badges (10 % tint over the raised surface).

| Pair (minimum)                            | Dark  | Light |
| ----------------------------------------- | ----- | ----- |
| on-surface on surface (4.5)               | 16.87 | 16.97 |
| on-surface on surface-raised (4.5)        | 16.12 | 17.72 |
| on-surface-muted on surface (4.5)         | 7.24  | 7.41  |
| on-surface-muted on surface-raised (4.5)  | 6.91  | 7.73  |
| on-surface-muted on surface-hover (4.5)   | 5.81  | 6.55  |
| on-surface-muted on surface-overlay (4.5) | 6.41  | 7.73  |
| primary on surface (4.5)                  | 8.19  | 4.96  |
| primary on surface-raised (4.5)           | 7.83  | 5.18  |
| on-primary on primary (4.5)               | 7.69  | 5.18  |
| on-primary on primary-hover (4.5)         | 10.43 | 7.31  |
| on-selected on surface-selected (4.5)     | 9.24  | 6.60  |
| on-surface on surface-selected (4.5)      | 14.04 | 16.01 |
| success on surface-raised (4.5)           | 10.17 | 7.13  |
| warning on surface-raised (4.5)           | 10.61 | 6.85  |
| danger on surface-raised (4.5)            | 6.40  | 6.47  |
| info on surface-raised (4.5)              | 6.97  | 6.70  |
| success on surface (4.5)                  | 10.64 | 6.83  |
| warning on surface (4.5)                  | 11.11 | 6.56  |
| danger on surface (4.5)                   | 6.70  | 6.20  |
| outline on surface (3)                    | 3.51  | 3.24  |
| outline on surface-raised (3)             | 3.36  | 3.38  |
| focus on surface (3)                      | 7.77  | 4.95  |
| focus on surface-raised (3)               | 7.42  | 5.17  |
| on-tooltip on tooltip (4.5)               | 16.12 | 16.97 |
| primary on surface-hover (3, icons only)  | 6.58  | 4.39  |

Found and fixed: the light theme's first success (green 700) and warning (amber 700) fell under 4.5:1 inside a tinted badge (axe in Storybook); they are now green 800 (`#166534`) and amber 800 (`#854d0e`).
