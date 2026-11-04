# Testing

## Layers

| Layer                                            | Where                                                                                                         | Run                                                             | Threshold                                                                       |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| Python domain (pure logic)                       | `services/*/tests/unit`                                                                                       | `uv run pytest`                                                 | total ≥ 90 %                                                                    |
| Database (repositories, migrations, constraints) | `services/api/tests/db` against Postgres (`make up`; CI service container; database name must end in `_test`) | `uv run pytest`                                                 | as above                                                                        |
| API (FastAPI + fakes for ports)                  | `services/api/tests/api`                                                                                      | `uv run pytest`                                                 | as above                                                                        |
| Worker (processors on sample files)              | `services/worker/tests`                                                                                       | `uv run pytest`                                                 | as above                                                                        |
| Blender core without `bpy` (v0.3)                | `dcc/blender-addon/tests`                                                                                     | `uv run pytest`                                                 | as above                                                                        |
| Storage integration                              | `services/api/tests/integration` against SeaweedFS (`make up`; CI starts it with compose)                     | `uv run pytest`                                                 | real POST policy, HEAD, outage                                                  |
| API contract                                     | `services/api/tests/unit/test_openapi_contract.py`                                                            | `uv run pytest`                                                 | committed `openapi.json` equals the app; run `make openapi` after route changes |
| UI components                                    | `packages/ui/src/**/*.test.tsx`                                                                               | `npm test -w @kiln/ui`                                          | lines ≥ 80 %                                                                    |
| Web units/components                             | `apps/web/src/**/*.test.ts(x)`                                                                                | `npm test -w @kiln/web`                                         | lines ≥ 80 %                                                                    |
| CLI                                              | `packages/cli/src/**/*.test.ts`                                                                               | `npm test -w @kiln/cli`                                         | lines ≥ 80 %                                                                    |
| Browser journeys                                 | `apps/web/e2e` (Playwright, desktop + mobile)                                                                 | `make e2e` (builds, serves with `vite preview`, starts the API) | smoke + the main journey of each feature                                        |
| Accessibility                                    | axe in `apps/web/e2e`                                                                                         | `make e2e`                                                      | serious/critical = 0 (WCAG 2.2 AA tags)                                         |
| Performance                                      | Lighthouse on the production build                                                                            | manual, every release                                           | LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1                                            |

`make ci` = lint + typecheck + test + build, identical to `.github/workflows/ci.yml`.

## Principles

- Test behaviour, one behaviour per test, Arrange–Act–Assert; test names are sentences (`test_upload_is_rejected_when_the_file_type_is_unknown`).
- Fakes for ports (database, storage, clock, Claude) in `tests/fakes.py`; no network in tests; warnings are errors.
- Small sample files in `samples/` (CC0 or self-made), never real studio assets.
- E2E runs against the production build, never the dev server.

## What the tests do not prove

- Tag quality from Claude: measured separately with a small hand-labelled eval set (`services/worker/evals/`), precision/recall reported in each release's changelog.
- That the add-on works inside a real Blender: checked by hand on Blender 4.2 LTS before every release that changes it.
- Performance with thousands of assets: measured only once a large seed exists (v0.4).
