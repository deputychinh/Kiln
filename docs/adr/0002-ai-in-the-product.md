# ADR 0002: AI in the product

- Status: accepted · 2026-11-03

## Context

Three features use a language model: (1) tags and a description from a thumbnail, (2) explaining naming-convention violations and suggesting the correct name, (3) turning a natural-language search ("rock textures approved last week") into structured filters. Risks: wrong output, growing cost, leaking client data, tests that depend on the network.

## Decision

1. **Claude through the Anthropic API**; model ids and prices live in `constants.py` / env. Defaults: a Sonnet model for vision tagging, a Haiku model for search planning (cheap, fast). Changing models is configuration, not code.
2. **Ports only**: `AiTagger` and `AiSearchPlanner`, each with a Claude adapter and a deterministic offline adapter (file name + dominant colours) used without a key and in tests.
3. **Structured output**: tool use with a JSON schema, parsed with pydantic; a schema mismatch fails the job with a reason instead of guessing.
4. **A person decides**: AI tags are stored as `suggested` and become `accepted` only when someone accepts them. Naming rules are deterministic code; AI only explains and suggests.
5. **Search**: the model may only return filters from an allow-list (tag, type, status, date range, author); the API builds a parameterised query itself and never runs model-generated SQL (A05).
6. **Cost and limits**: call only for a new version; cache by file hash; monthly budget `KILN_AI_MONTHLY_BUDGET_USD`, after which the offline adapter takes over and the UI says so.
7. **Data**: send only a 512 px thumbnail and the file name, never user metadata; log token counts and latency, never content.
8. **Measure quality**: `services/worker/evals/` holds about 50 hand-labelled assets; precision/recall of tags is reported in every release's changelog.

## Consequences

- Without a key the product still works end to end (with weaker tags); CI needs no secret.
- An `ai_usage` table tracks spend against the budget.
- Every prompt or model change reruns the eval and records the result.

## Sources

`references/security.md` (A05, A10), `references/data-and-reliability.md` (timeouts, caching), Anthropic documentation on tool use and vision.
