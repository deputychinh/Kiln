# ADR 0001: Stack and repository layout

- Status: accepted · 2026-11-03

## Context

Kiln is a review hub for small studios (5–50 people): artists publish images, textures and 3D models; leads compare versions and approve; AI tags assets and catches naming mistakes. It is also a portfolio piece for a full-stack role (React/TypeScript, Node tooling, Python pipelines, DCC integration), so every part must be real enough to demo, and it ships weekly.

## Decision

1. **One repository, two workspaces.** npm workspaces for `apps/web`, `packages/ui`, `packages/cli`; a uv workspace for `services/api` and `services/worker`. Repo tooling (Prettier, husky, commitlint, ESLint, Stylelint) lives at the root. _npm rather than pnpm_: Node 26 no longer ships corepack and both reference repos use npm; switching later is one commit.
2. **Modular monolith first** (`references/backend-architecture.md`): one FastAPI API with bounded contexts `assets` (core: asset, version, file), `review` (annotations, comments, approval) and `catalog` (tags, search, naming rules). The worker is a separate process because heavy work (rendering, AI calls) must never block a request.
3. **Layers**: routes → services → domain; I/O behind ports (`AssetRepository`, `ObjectStorage`, `JobQueue`, `AiTagger`, `Clock`). The domain is pure and tested without a database.
4. **Data**: Postgres 17 (SQLAlchemy 2 + Alembic) for metadata; files in S3-compatible object storage (MinIO locally). Uploads and downloads use **presigned URLs**, so asset bytes never pass through the API.
5. **Job queue on Postgres** (`SELECT … FOR UPDATE SKIP LOCKED`), with the job written in the same transaction as the asset change (an outbox in effect, `references/data-and-reliability.md`). No Redis/Kafka until an ADR shows the need. Workers are idempotent per `job_id`, retry with backoff, and after 5 attempts mark the job `failed`, which the UI shows.
6. **API** per `references/api-design.md`: OpenAPI 3.1 exported by `make openapi`, web types generated with `openapi-typescript`; RFC 9457 errors with `code`; cursor pagination; `Idempotency-Key` on `POST /assets`; `/health`, `/ready`; `X-Request-Id`.
7. **Web**: React 19 + Vite as an SPA (no SSR: it is a signed-in tool), TanStack Router (typed routes, state in the URL) and TanStack Query (server state). 3D viewer: react-three-fiber. Styling: plain CSS with `packages/ui` tokens and BEM; no Tailwind, to match the house conventions.
8. **Own design system** (`packages/ui`) with Storybook: the evidence for "visual consistency" and the only place tokens are defined.
9. **Node CLI** (`packages/cli`, Commander) and **Blender add-on** use the same public API as the web app, authenticated with personal access tokens.
10. **Quality gates**: ruff + mypy strict + pytest ≥ 90 %; ESLint 0 warnings + Stylelint + tsc + Vitest ≥ 80 % + Playwright + axe; Conventional Commits enforced by husky and CI.

## Consequences

- One `make ci` checks both ecosystems; CI has two jobs (`python`, `node`).
- Postgres as a queue tops out at tens of jobs per second; enough for a small studio, a new ADR if exceeded.
- Presigned URLs require bucket CORS and size/type limits at signing time (A10, `docs/security.md`).
- Authentication: v0.1 runs in single-user demo mode; v0.2 adds email + password sign-in (Argon2id, HttpOnly session cookie) and personal access tokens for the CLI and Blender (KILN-12).
- No SSR, so any public marketing page is built separately; acceptable because the product sits behind sign-in.
- A UI library inside an npm workspace can pull a second React copy if versions drift; versions are pinned identically and `npm ls react` must show one.

## Sources

`references/backend-architecture.md` (Clean Architecture, monolith first), `references/api-design.md` (Zalando guidelines, RFC 9457), `references/data-and-reliability.md` (DDIA ch. 11, Release It! timeouts and backoff), `references/frontend-and-ux.md`, `references/delivery.md`.
