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

1. The client (the web app's upload panel since KILN-26: at most 2 files at a time, one idempotency key per file, progress through `XMLHttpRequest`; or the API directly) calls `POST /api/v1/assets` (optional `Idempotency-Key`; the key row and the asset are written in one transaction, so a retry replays the first result — KILN-21); the API creates `Asset` + `AssetVersion(pending_upload)` and returns a presigned POST (ADR 0004: 15-minute expiry; the policy pins the key, content type and exact size).
2. The client POSTs the file as multipart form data to its **staging key** `uploads/<asset_id>/<version_id>`, then calls `POST /api/v1/asset-versions/{id}/completions`.
3. The API `HEAD`s the staging object, checks size and type, copies it to the final key with `CopySourceIfMatch` (ADR 0005), deletes the staging object, moves the version to `processing` records the final object's ETag and writes a `thumbnail` job in the same transaction (outbox).
4. The worker claims the job (`FOR UPDATE SKIP LOCKED`, 5-minute lease), checks the final object's ETag against the one recorded at completion, renders a 512 px WebP to `thumbs/<asset_id>/<version_id>.webp` (images with Pillow; `.glb` models with its own glTF reader and a numpy/Pillow flat-shaded renderer, no GPU, inside a disposable child process: 60 s wall clock, 65 s CPU, 2 GiB address space on Linux (macOS bounds only time), exits if the worker dies — KILN-5, ADR 0007; give the worker a stop grace period of at least 70 s), and in one transaction marks the version `ready`, updates the asset cover and finishes the job. Permanent problems mark the version `failed` with a reason; transient ones retry with backoff (5/25/125/625 s) and give up after 5 attempts; leases use the database clock and every job update is guarded by its claim, so several workers and crashed workers are safe. A running job extends its lease every 100 s (a third of the lease) through the same claim guard and stops after 30 minutes, so long jobs are not taken twice and hung ones are still released (KILN-24); an expired lease is never extended, the heartbeat stops before any outcome is written, and reaping an exhausted job re-checks that its lease is still expired. (v0.3 adds AI tagging to this step.) The web app polls the asset every 3 s while a version is processing (KILN-6, for at most 5 minutes); server-sent events can replace polling once there are many viewers.

Preview downloads are signed with botocore's SigV4 signer pinned to the start of the current 10-minute window (`kiln_api/signing.py`, ADR 0008), so a preview keeps one URL for the window and the browser serves repeat views from its cache (`Cache-Control: private, max-age=1500, immutable`); each URL is valid 25 minutes, at least 15 after it is handed out (KILN-27).

5. Maintenance (KILN-22): at most once an hour across all workers (a lease row `maintenance_runs` updated in one statement on the database clock), the worker expires versions still `pending_upload` after 24 h (`failed`, `UPLOAD_EXPIRED`, saved before their staging object — and a final object a racing completion may have promoted — is deleted), deletes `uploads/` objects older than 24 h whose version is gone or no longer waiting (only keys of the form `uploads/<uuid>/<uuid>`), and purges idempotency keys past their 24 h window — at most 500 expiries and 500 deletions per run, a listing cut after 5,000 keys, versions looked up 100 at a time. A completion that loses the race to an expiry deletes the file it promoted, so neither order leaves an object behind. The worker process is a supervisor that runs the loop in a `spawn`ed child and replaces it after 200 jobs or 1 GiB of peak memory (Pillow keeps freed memory mapped), or after a crash with a 1–30 s backoff and jitter; a child whose supervisor dies stops after its current job (KILN-25). Maintenance runs inline in the job loop, so a run pauses job processing for its duration (seconds at these batch sizes). Failures are logged and never stop job processing; a later run finishes what an interrupted one left.

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
- Errors: RFC 9457 + `code`; the web app reacts to the status and `code`, never to message text (it shows the problem `title`).
- Observability: JSON logs with `request_id` / `job_id`; `/health`, `/ready`; job metrics (queued, failed).
- Timeouts: Postgres connect 5 s, lock 5 s and statement 15 s; storage 3 s connect and 10 s read with 2 attempts in total (worst case 26 s); Claude 30 s; every retry loop has backoff and a cap.
- Storage resilience (KILN-23): every network call to storage (API and worker) goes through a circuit breaker — open after 5 consecutive failures, fail fast for 30 s with `Retry-After` set to the time left, then one trial call — and a bulkhead of 16 concurrent calls with a 0.5 s wait. Signing URLs is local and never blocked, so the gallery keeps working during an outage; `/ready` fails at once while the circuit is open, but its 1 s probes never count toward opening it. The bulkhead (16, validated ≤ 32) stays below AnyIO's 40-thread pool, so requests that do not wait on storage always find a thread. Listings are guarded per page fetch, the network call, not per key.

Updated with every ADR in `docs/adr/`.
