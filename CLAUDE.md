# Kiln

AI-assisted review and publishing hub for creative studios: artists publish images, textures and 3D models from Blender or a CLI, leads compare versions and approve, and Claude tags assets and flags naming-convention mistakes.

Stack: npm workspaces (React 19 + Vite + TypeScript web app, design system, Node CLI) + uv workspace (FastAPI API, Python worker) + Blender add-on; Postgres + MinIO. Docs language: English. Everything below is binding for every session in this repo.

## Repo map

| Folder              | What                                                    | Commit scope   |
| ------------------- | ------------------------------------------------------- | -------------- |
| `apps/web`          | React 19 + Vite + TanStack Router/Query                 | `web`          |
| `packages/ui`       | design system: tokens, components (Storybook from v0.1) | `ui`           |
| `packages/cli`      | Node CLI `kiln` (publish, validate)                     | `cli`          |
| `services/api`      | FastAPI, Postgres, MinIO                                | `api`, `db`    |
| `services/worker`   | Python: thumbnails, validation, AI tagging              | `worker`, `ai` |
| `dcc/blender-addon` | Blender add-on "Publish to Kiln" (v0.3)                 | `blender`      |

## Sources of truth (read before changing code)

| Topic                                                       | Read                                                                     |
| ----------------------------------------------------------- | ------------------------------------------------------------------------ |
| Code conventions, naming, folder layout                     | `docs/conventions.md`                                                    |
| Testing: which layer, where it runs, thresholds             | `docs/testing.md`                                                        |
| Why this stack and layout; every decision with consequences | `docs/adr/` (a new decision is a new file; accepted ADRs are not edited) |
| Current architecture                                        | `docs/architecture/README.md`                                            |
| Threat model and security baseline                          | `docs/security.md`                                                       |
| Tokens, components, layout per window size                  | `docs/design-system.md`                                                  |
| What is being built now and next                            | `docs/plan.md`, `docs/backlog.md`                                        |
| Commands                                                    | `make help`                                                              |

## Commands

```sh
make install   # npm workspaces + uv workspace
make lint      # format check + lint + typecheck for every part
make test      # unit + API/component tests with coverage
make ci        # lint + test + build: exactly what GitHub Actions runs
make e2e       # Playwright against the production build and the real API
```

Do not call npm/uv directly when a Makefile target exists, except while debugging that target.

## Definition of done

A task is reported done only when all of these hold:

1. Code follows `docs/conventions.md` (0 lint warnings, clean typecheck).
2. New behaviour or a fixed bug has a test; coverage stays above the thresholds in `docs/testing.md`.
3. `make ci` is green and the result (test counts) is pasted in the report; UI changes also pass `make e2e`.
4. Docs change in the same commit: `CHANGELOG.md` under `[Unreleased]`, README when usage changes, a new ADR when a decision changes.
5. It is committed (routine below).

## Routine for every turn (mandatory)

Every turn that changes files ends with a commit:

1. Run the gates of every part touched (`make lint && make test`, or that part's equivalent).
2. Update CHANGELOG / docs in the same change.
3. `git add` exactly the files of that task (no `git add -A` when the tree has unrelated files), then `git commit` with a Conventional Commit whose scope is in `commitlint.config.mjs`:
   - `feat(web): …`, `fix(api): …`, `test(e2e): …`, `docs(plan): …`, `chore(repo): …`
   - One commit per complete unit of work (code + tests + docs). Several commits per turn are fine.
   - Subjects are lower-case; the body ends with `Refs: KILN-<n>`.
4. Commit only when green. If a gate is red at the end of the turn: **do not commit**; say what fails and why, and leave the tree dirty on purpose.
5. Push to `origin main` after committing (the owner asked for every commit to be pushed). Never force-push or rewrite history on `main`.
6. End the report with the hash and message of each new commit.

## Delivery loop (how work happens here)

Work the backlog with the `/deliver-loop` skill, without waiting for the owner between items:
BA story in `docs/stories/KILN-<n>.md` (Given/When/Then ACs, cited references) → design → tests first, then code →
QA (`make ci`, `make e2e`, screenshots at 390 and 1280 px, AC → test traceability) → independent reviewer scores the
change on the 10-point rubric (`~/.claude/skills/deliver-loop/rubric.md`) → improve until ≥ 9/10 → commit with
`Score: x/10` in the body, push → one-line retro → next item. Stop only for blockers only the owner can solve.

## Jira and releases

- Every task has an id `KILN-<n>` in `docs/backlog.md` (and in Jira once linked); branches are `feat/KILN-12-short-name` when not committing straight to `main`.
- One release per week, `v0.x`: rename `[Unreleased]` in `CHANGELOG.md` to the version and date, commit `chore(release): v0.x.0`, tag `v0.x.0`, push the tag.

## AI in the product

- Claude is called only through the `AiTagger` / `AiSearchPlanner` ports in `services/*`; tests use fakes and never reach the network.
- Model output always goes through a pydantic schema and a person accepts it before it becomes official data.
- Model ids, token limits and prices live in `constants.py` / env, never scattered in code. See ADR 0002.

## Working style

- Finish a whole phase (`docs/plan.md`) without stopping to ask; ask only for what only the owner knows (business rules, secrets, choosing between two patterns that both exist in the repo).
- Smallest change that satisfies the request; no refactors outside scope; no new library when the stack already has a way.
- Never swallow errors; domain errors carry a stable code and are mapped to HTTP/UI exactly once, at the boundary.
- Never log personal data, secrets, tokens or asset contents. `.env` never enters git; `.env.example` lists every key.
- Display strings live in locale files, never hard-coded in components.
- For UI work, take a screenshot or run e2e; do not describe it from memory.
- React must exist once in the tree: pin the same `react`/`react-dom` version in every workspace (`npm ls react` shows one version).

## Language

When the owner writes Vietnamese, answer in Vietnamese; technical names, commands, commit messages and all repo docs stay in English.
