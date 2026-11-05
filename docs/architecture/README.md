# Architecture

```mermaid
flowchart LR
  subgraph Clients
    web[Web app<br/>React + Vite]
    cli[kiln CLI<br/>Node]
    blender[Blender add-on]
  end
  web & cli & blender -->|HTTPS /api/v1 JSON| api[API<br/>FastAPI]
  api --> db[(Postgres<br/>metadata + jobs)]
  api -.->|signs presigned URLs| s3[(Object storage<br/>S3 (SeaweedFS locally))]
  web & cli & blender -->|POST/GET files| s3
  worker[Worker<br/>Python] -->|SKIP LOCKED| db
  worker --> s3
  worker -->|vision, tool use| claude[Claude API]
```

## Upload flow (v0.1)

1. The client calls `POST /api/v1/assets` (optional `Idempotency-Key`; the key row and the asset are written in one transaction, so a retry replays the first result — KILN-21); the API creates `Asset` + `AssetVersion(pending_upload)` and returns a presigned POST (ADR 0004: 15-minute expiry; the policy pins the key, content type and exact size).
2. The client POSTs the file as multipart form data to its **staging key** `uploads/<asset_id>/<version_id>`, then calls `POST /api/v1/asset-versions/{id}/completions`.
3. The API `HEAD`s the staging object, checks size and type, copies it to the final key with `CopySourceIfMatch` (ADR 0005), deletes the staging object, moves the version to `processing` records the final object's ETag and writes a `thumbnail` job in the same transaction (outbox).
4. The worker claims the job (`FOR UPDATE SKIP LOCKED`, 5-minute lease), checks the final object's ETag against the one recorded at completion, renders a 512 px WebP to `thumbs/<asset_id>/<version_id>.webp`, and in one transaction marks the version `ready`, updates the asset cover and finishes the job. Permanent problems mark the version `failed` with a reason; transient ones retry with backoff (5/25/125/625 s) and give up after 5 attempts. (v0.3 adds AI tagging to this step.) The web app polls or listens on SSE `/api/v1/events`.

## Endpoints (v0.1)

| Method and path                                        | Result                                                                                                                     |
| ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------- |
| `POST /api/v1/assets`                                  | `201` asset + version 1 + signed upload, `Location: /api/v1/assets/{id}`                                                   |
| `GET /api/v1/assets?limit=&cursor=`                    | newest-first page `{items, next_cursor}`                                                                                   |
| `GET /api/v1/assets/{asset_id}`                        | asset with `versions`                                                                                                      |
| `POST /api/v1/assets/{asset_id}/versions`              | `201` next version + signed upload, `Location: /api/v1/asset-versions/{id}`                                                |
| `GET /api/v1/asset-versions/{version_id}`              | one version                                                                                                                |
| `POST /api/v1/asset-versions/{version_id}/completions` | `200` version in `processing` (idempotent); `409 UPLOAD_NOT_FOUND / UPLOAD_MISMATCH`                                       |
| `GET /health`, `GET /ready`                            | liveness; readiness of Postgres (`SELECT 1`) and storage (1 s `HeadBucket`, one attempt) (`503` problem details otherwise) |

## Bounded contexts

| Context  | Kind       | Main entities                         |
| -------- | ---------- | ------------------------------------- |
| assets   | core       | Asset, AssetVersion, StoredFile       |
| review   | core       | Review, Annotation, Comment, Decision |
| catalog  | supporting | Tag, NamingRule, SearchPlan           |
| identity | generic    | User, Session, AccessToken (v0.2)     |

## Boundaries

| Boundary        | Contract                                                                        | Owner  |
| --------------- | ------------------------------------------------------------------------------- | ------ |
| clients → api   | OpenAPI (`services/api/openapi.json`, generated TS types in `apps/web/src/api`) | api    |
| api ↔ worker    | `jobs` table (`kind`, schema-checked JSON `payload`, `attempts`, `run_after`)   | api    |
| worker → Claude | `AiTagger` port, tool schemas in `kiln_worker/ai/schemas.py`                    | worker |
| web ↔ ui        | exports of `@kiln/ui` (components + `tokens.css`)                               | ui     |

## Cross-cutting

- Configuration from `KILN_*` env, validated at start-up (pydantic-settings); `.env.example` lists every key.
- Errors: RFC 9457 + `code`; the web app reacts to `code`, never to message text.
- Observability: JSON logs with `request_id` / `job_id`; `/health`, `/ready`; job metrics (queued, failed).
- Timeouts: Postgres lock 5 s and statement 15 s; storage 3 s connect and 10 s read with 2 attempts in total (worst case 26 s); Claude 30 s; every retry loop has backoff and a cap.

Updated with every ADR in `docs/adr/`.
