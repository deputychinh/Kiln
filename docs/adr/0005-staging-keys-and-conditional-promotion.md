# ADR 0005: Staging keys and conditional promotion of uploads

- Status: accepted · 2026-11-04 · extends ADR 0004

## Context

ADR 0004 signs a POST form that is valid for 15 minutes. The KILN-3 review showed that the same form can be posted again after the upload was confirmed, replacing the bytes that were checked (an uploader could swap a reviewed texture). A storage `HEAD` followed by a separate read is also a time-of-check/time-of-use gap.

## Decision

1. The signed form writes only to a **staging key** `uploads/<asset_id>/<version_id>`; nothing downstream (thumbnails, AI, reviewers) reads staging keys.
2. Completion `HEAD`s the staging object, checks the declared size and type, then **copies it server-side to the final key** `assets/<asset_id>/v<n>/<version_id>.<ext>` with `CopySourceIfMatch: <ETag from HEAD>`. If the object changed in between, S3 answers `412` and the API returns `409 UPLOAD_MISMATCH`.
3. The staging object is deleted after the copy. A later reuse of the form only recreates a staging object that nothing reads (an orphan purged by the worker in KILN-4).
4. Completion is resumable: if the copy succeeded but the delete or the status save failed, a retry finds the final object and finishes.

A spike against SeaweedFS 4.48 confirmed `CopySourceIfMatch` returns `412 PreconditionFailed` when the source changed.

## Consequences

- Each upload costs one extra server-side copy (no bytes through the API).
- Orphaned staging objects need a purge (KILN-4).
- Final objects are written only by the API, never by clients.

## Sources

[AWS CopyObject conditional headers](https://docs.aws.amazon.com/AmazonS3/latest/API/API_CopyObject.html), `references/security.md` (A04/A08 integrity, A06 insecure design), KILN-3 review round 1.
