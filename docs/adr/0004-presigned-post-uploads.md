# ADR 0004: Presigned POST instead of presigned PUT for uploads

- Status: accepted · 2026-11-04 · amends ADR 0001 §4

## Context

ADR 0001 said uploads go through presigned URLs. A presigned **PUT** signs a URL for one key but cannot bound the body size: S3's `content-length-range` condition exists only in **POST** policies. Kiln accepts files up to 500 MB from browsers, the CLI and Blender, and must not let a client write a different size or type than it declared.

## Decision

Uploads use a presigned **POST** (SigV4 policy, `multipart/form-data`). The policy pins the exact object key, the `Content-Type`, and `content-length-range` to exactly the declared size; it expires after 15 minutes. On completion the API still `HEAD`s the object and compares size and type (defence in depth for S3 servers that ignore a condition).

A spike on 2026-11-04 (recorded in `docs/stories/KILN-3.md`) showed SeaweedFS 4.48 enforcing every condition: one byte too many → `EntityTooLarge`, too few → `EntityTooSmall`, other type or key → `403`.

## Consequences

- Clients send a form (`url` + `fields` + file) rather than a raw body; the CLI and add-on use the same shape.
- Multipart uploads above 5 GB are not possible with one POST; the 500 MB limit stays well below.
- Bucket CORS must allow `POST` from the web origin (KILN-6).

## Sources

[AWS: creating a POST policy](https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-HTTPPOSTConstructPolicy.html), [How to use S3 POST signed URLs](https://advancedweb.hu/how-to-use-s3-post-signed-urls/), `references/security.md` (A10 limits).
