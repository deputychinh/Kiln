# ADR 0003: SeaweedFS for local object storage

- Status: accepted · 2026-11-03 · amends ADR 0001 §4

## Context

ADR 0001 named MinIO for local S3-compatible storage. MinIO no longer publishes images to Docker Hub (`docker pull minio/minio` fails with "pull access denied") and its community repository has been archived, so the compose file could not start.

## Decision

Use **SeaweedFS** (`chrislusf/seaweedfs:4.48`, Apache-2.0) in `server -s3` mode for local development and CI. Credentials come from `infra/seaweedfs/s3.json` and match `.env.example`. Production targets any S3 API (AWS S3, Cloudflare R2, Garage). The application talks only to the S3 API through the `ObjectStorage` port and creates its bucket on start-up when it is missing, so the storage server is swappable without code changes.

Alternatives considered: RustFS (young, alpha releases), Garage (AGPL, needs a layout step before first use), S3Proxy (in-memory only, good for unit tests, not for manual testing), a third-party MinIO mirror (not published by MinIO, supply-chain risk, A03).

## Consequences

- S3 is served on `:8333`; there is no bundled web console (MinIO's was on `:9001`).
- Bucket creation moves into the app (`ensure_bucket` at start-up) instead of a console click.
- Presigned URLs, CORS and size limits must be checked against SeaweedFS in e2e, not assumed from MinIO behaviour.

## Sources

[MinIO archived, self-hosted alternatives](https://pinggy.io/blog/minio_archived_self_hosted_s3_alternatives/), [MinIO Docker image changes](https://www.minimus.io/post/minio-docker-image-changes-how-to-find-a-secure-minio-alternative), [SeaweedFS S3 API](https://github.com/seaweedfs/seaweedfs/wiki/Amazon-S3-API).
