# Kiln

**AI-assisted review and publishing hub for creative studios.** Artists publish images, textures and 3D models from Blender or a CLI; leads compare versions side by side and approve; Claude tags every asset and flags naming-convention mistakes before they reach the pipeline.

| Gallery                   | Review                    |
| ------------------------- | ------------------------- |
| _(screenshot after v0.1)_ | _(screenshot after v0.2)_ |

## Quick start

Requires Python 3.12 + [uv](https://docs.astral.sh/uv/), Node ≥ 24 and Docker.

```sh
make install   # npm workspaces + uv workspace
make up        # Postgres + SeaweedFS
make migrate   # database schema
make api       # API on :8000 (own terminal)
make worker    # previews and maintenance (own terminal)
make web       # web app on http://localhost:5173 (own terminal)
```

`make help` lists every command.

## Features by release

| Release | Scope                                                                                                                |
| ------- | -------------------------------------------------------------------------------------------------------------------- |
| v0.1    | Upload images and `.glb` files, gallery, asset detail, worker-generated thumbnails                                   |
| v0.2    | Versions, side-by-side compare, 3D viewer, region annotations, comments, approval states, sign-in                    |
| v0.3    | Claude tagging and descriptions, naming-convention lint, natural-language search, Blender add-on, `kiln publish` CLI |
| v0.4    | Polish: UI consistency audit, WCAG 2.2 AA, Core Web Vitals, public Storybook, case study                             |

## Architecture

```mermaid
flowchart LR
  blender[Blender add-on] -->|HTTP| api
  cli[kiln CLI] -->|HTTP| api
  web[Web app<br/>React + Vite] -->|HTTP /api/v1| api[API<br/>FastAPI]
  api --> db[(Postgres)]
  api -->|presigned URLs| s3[(S3 (SeaweedFS locally))]
  api -->|jobs table| worker[Worker<br/>Python]
  worker --> s3
  worker -->|vision| claude[Claude API]
```

More: [architecture](docs/architecture/README.md) · [decisions](docs/adr) · [conventions](docs/conventions.md) · [testing](docs/testing.md) · [security](docs/security.md) · [design system](docs/design-system.md) · [plan](docs/plan.md).

## Quality

`make ci` runs lint, typecheck, tests and builds for every part (thresholds in `docs/testing.md`); GitHub Actions runs the same. `make e2e` runs Playwright with axe accessibility checks against the production build and the real API; `make e2e-ui` runs axe over every Storybook story in both themes. Commits follow Conventional Commits, enforced by husky + commitlint, and a release ships every week with a changelog.

## Structure

```
apps/web/            React 19 + Vite + TanStack Router/Query
packages/ui/         design tokens and components
packages/cli/        Node CLI `kiln`
services/api/        FastAPI (SQLAlchemy + Alembic from v0.1)
services/worker/     thumbnails, validation, AI tagging
dcc/blender-addon/   Blender "Publish to Kiln" add-on (v0.3)
docs/                plan, ADRs, architecture, conventions, testing
```

## Built with AI

Kiln is developed with Claude Code: agent rules live in `CLAUDE.md`, every working turn ends in a green, conventional commit, and each pull request notes what was AI-generated and what was reviewed or rewritten by hand. How the product itself uses Claude is in [ADR 0002](docs/adr/0002-ai-in-the-product.md).

## Licence and data

Code: MIT. Sample assets in `samples/` are self-made or CC0, with sources in `samples/README.md`. No client assets are ever committed.
