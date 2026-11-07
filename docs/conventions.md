# Conventions

Lint enforces most of these rules; the rest is checked in review.

## General

- **Single source of truth**: enums, constants, errors and shared interfaces are declared in exactly one place (Python: each package's `enums.py`, `constants.py`, `errors.py`; TypeScript: `src/enums/*.enum.ts`, `src/constants/*.constant.ts`, `src/interfaces/*.interface.ts`) and imported everywhere else.
- **Dependencies point inward**: routes → services → domain; the domain never imports a framework, the database or an SDK.
- **Python = classes + SOLID; TypeScript = arrow functions + design tokens + BEM.**
- Errors are never swallowed; domain errors carry a stable code (`ErrorCode`) and are mapped to HTTP/UI exactly once, at the boundary (the API returns RFC 9457 problem details with a `code` field). `errors.py` stays framework-free; the HTTP mapping lives in `problems.py`.
- No personal data, secrets, tokens or asset contents in logs.
- Formatting: Prettier (100 columns, single quotes, trailing commas); Python: ruff format (100 columns).
- Times are UTC ISO-8601; ids are UUID v7 strings (time-ordered); the JSON API uses `snake_case`, and the web app reads it through types generated from OpenAPI.
- Code, identifiers, commits, docs and source UI copy are in English; Vietnamese is a second locale.

## Python (`services/*`, uv workspace)

| Topic         | Rule                                                                                                                                                                                                                                                                                                                   |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| API layout    | `kiln_api/{config.py, enums.py, constants.py, errors.py, problems.py, domain/, ports.py, adapters.py, resilience.py, signing.py, clock.py, authentication.py, cli.py, repositories/, services/, routes/, schemas/, db/, container.py, main.py}`; authorization is decided only in `domain/authorization.py` (ADR 0012) |
| Worker layout | `kiln_worker/{config.py, constants.py, enums.py, errors.py, runner.py, thumbnail.py, glb.py, model_preview.py, sandbox.py, heartbeat.py, watchdog.py, maintenance.py, recycle.py, supervisor.py, process.py, __main__.py}`; ports, adapters and models come from `kiln_api` rather than being copied                   |
| Types         | mypy `strict`; no `Any`; `frozen=True, slots=True` dataclasses for values; pydantic only at the API boundary and for AI output                                                                                                                                                                                         |
| Lint          | ruff with the rule set in the root `pyproject.toml`; every `noqa` states a reason                                                                                                                                                                                                                                      |
| Classes       | constructor injection, `_private` attributes, one reason to change; services receive abstract ports                                                                                                                                                                                                                    |
| Tests         | `tests/unit` for the domain, `tests/api` through `TestClient` with fakes for ports; test names are sentences; coverage ≥ 90 %                                                                                                                                                                                          |
| Data          | Alembic is the only way to change the schema; every migration is reversible; dropping a column or table needs an ADR                                                                                                                                                                                                   |
| AI            | Claude only through ports; output parsed by pydantic; never send personal data to a model                                                                                                                                                                                                                              |

## TypeScript (`apps/web`, `packages/*`)

| Topic             | Rule                                                                                                                                                                                                                                                                                                                                               |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Web layout        | `src/routes` (TanStack Router file routes), `src/features/<name>/{components,hooks,services}`, `src/components` (app-level shared), `src/api` (generated schema), `src/config`, `src/constants`, `src/enums`, `src/interfaces`, `src/hooks`, `src/locales`, `src/styles`                                                                           |
| UI package layout | `src/tokens/tokens.css`, `src/components/<Name>/{<Name>.tsx,<Name>.css,<Name>.test.tsx,<Name>.stories.tsx}` (a stories file is required: `src/stories.test.tsx`); story-only decorators and sample data live in `.storybook/` (imported as `#storybook/*`), never in `src/`, `src/enums`, `src/index.ts`; internal imports use the `#ui/*` subpath |
| Functions         | arrow functions only; no classes; no `any`; no non-null `!`; `@/` alias in apps, no `../../`                                                                                                                                                                                                                                                       |
| CSS               | BEM, block = file name (`AssetCard.css` ↔ `.asset-card`); colour, spacing, type, radius, shadow, z-index and duration come only from `var(--kiln-…)` tokens; mobile-first                                                                                                                                                                          |
| State             | server state with TanStack Query in the feature's hooks; the selected item lives in the URL; local state with `useState/useReducer`; `useEffect` only to sync with external systems                                                                                                                                                                |
| UI                | every data view has loading / empty / error / success; colour is never the only signal; full keyboard support; targets ≥ 24 px, primary actions 44 px                                                                                                                                                                                              |
| Copy              | no hard-coded display strings; `src/locales/en.ts` is the source, `vi.ts` has the same keys (tested)                                                                                                                                                                                                                                               |
| Tests             | Vitest + Testing Library by role/label; line coverage ≥ 80 %; Playwright for main journeys against the production build                                                                                                                                                                                                                            |
| CLI               | `packages/cli`: commands are pure functions over injected I/O; exit codes in `exit-code.enum.ts`; relative imports with `.js` extensions (Node ESM)                                                                                                                                                                                                |
| Dependencies      | exact versions; `react`/`react-dom` pinned to the same version in every workspace so only one copy is installed                                                                                                                                                                                                                                    |

## Blender add-on (`dcc/blender-addon`, from v0.3)

- Targets Blender 4.2 LTS+ as an extension (`blender_manifest.toml`); logic that does not need `bpy` lives in `kiln_blender/core.py` and is tested with pytest outside Blender.
- Never block Blender's UI: uploads run on a background thread and report progress through the window manager.

## Commits, branches, releases

- Conventional Commits with lower-case subjects; scopes in `commitlint.config.mjs`. One commit per complete unit of work (code + tests + docs). The body ends with `Refs: KILN-<n>`.
- husky runs Prettier (pre-commit) and commitlint (commit-msg); CI runs both again.
- A change of behaviour or decision updates the ADR/docs in the same commit.
- Trunk-based: short-lived `feat/KILN-12-…` / `fix/KILN-…` branches, or straight to `main` when working alone; CI must be green before merging.
- Weekly release: `chore(release): v0.x.0` renames `[Unreleased]`, then tag `v0.x.0`.
