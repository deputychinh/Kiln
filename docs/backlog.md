# Backlog

Ids are `KILN-<n>`; once Jira is linked, the Jira key matches the id here.

| Id      | Release | Item                                                                                                                                     | Status |
| ------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| KILN-1  | –       | Repo bootstrap, conventions, CI, walking skeleton                                                                                        | done   |
| KILN-2  | v0.1    | `Asset` / `AssetVersion` model, first migration, repository                                                                              | done   |
| KILN-3  | v0.1    | Upload through presigned URLs (S3) + upload completion                                                                                   | done   |
| KILN-21 | v0.1    | `Idempotency-Key` replay for `POST /assets` (24 h, stored response)                                                                      | done   |
| KILN-4  | v0.1    | Postgres job queue (`SKIP LOCKED`, lease, backoff) + worker image thumbnails; ETag recorded at completion and verified before processing | done   |
| KILN-22 | v0.1    | Scheduled maintenance in the worker: purge orphaned `uploads/` staging objects and expired idempotency keys                              | todo   |
| KILN-23 | v0.1    | Circuit breaker / bulkhead around storage calls in the API                                                                               | todo   |
| KILN-24 | v0.1    | Lease heartbeat for worker jobs longer than the 5-minute lease                                                                           | todo   |
| KILN-25 | v0.1    | Recycle the worker process after N jobs (Pillow keeps freed memory mapped)                                                               | todo   |
| KILN-5  | v0.1    | Thumbnails for `.glb` (offscreen render)                                                                                                 | todo   |
| KILN-6  | v0.1    | Gallery + asset detail, four states, cursor pagination, adaptive navigation                                                              | done   |
| KILN-7  | v0.1    | Storybook for the design system                                                                                                          | todo   |
| KILN-26 | v0.1    | Upload from the browser: dropzone + file button, progress, completion; e2e upload → thumbnail visible                                    | todo   |
| KILN-27 | v0.1    | Stable signed thumbnail URLs within a time window so browsers can cache previews                                                         | todo   |
| KILN-8  | v0.2    | Asset versions + side-by-side compare                                                                                                    | todo   |
| KILN-9  | v0.2    | 3D viewer (react-three-fiber)                                                                                                            | todo   |
| KILN-10 | v0.2    | Region annotations on images + comments                                                                                                  | todo   |
| KILN-11 | v0.2    | Approval states and history                                                                                                              | todo   |
| KILN-12 | v0.2    | Sign-in (Argon2id, session cookie) + personal access tokens                                                                              | todo   |
| KILN-13 | v0.3    | Claude vision tags + descriptions, accepted by a person                                                                                  | todo   |
| KILN-14 | v0.3    | Naming-convention lint (rules configured per project)                                                                                    | todo   |
| KILN-15 | v0.3    | Natural-language search → filters (tool use)                                                                                             | todo   |
| KILN-16 | v0.3    | Blender add-on "Publish to Kiln"                                                                                                         | todo   |
| KILN-17 | v0.3    | CLI `kiln publish` / `kiln validate`                                                                                                     | todo   |
| KILN-18 | v0.3    | Tag quality eval                                                                                                                         | todo   |
| KILN-19 | v0.4    | UI consistency audit + a11y + Core Web Vitals                                                                                            | todo   |
| KILN-20 | v0.4    | Public Storybook, demo video, case study                                                                                                 | todo   |
