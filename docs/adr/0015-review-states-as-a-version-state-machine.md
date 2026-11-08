# ADR 0015: Review states as a per-version state machine with compare-and-set and an append-only history

- Status: accepted · 2026-11-08

## Context

KILN-11 adds approval. Leading tools model it differently: Frame.io puts one status label on an asset (Needs Review, In Progress, Approved); ShotGrid gives every Version a status that starts at "Pending Review"; Figma marks a frame "Ready for dev" and flags it "Changed" when it is edited afterwards; GitHub records reviews (`APPROVED`, `CHANGES_REQUESTED`) on a pull request and needs a body to request changes. Kiln's unit of review is the version (comments already belong to one, KILN-10), two leads may act on the same version at once, and a studio needs to know who approved what and when.

## Decision

1. **State per version, derived per asset.** `asset_versions.review_state` is `in_review` (default), `approved` or `changes_requested`. An asset's state is its newest version's, so uploading a version puts the asset back in review (ShotGrid's new Version is "Pending Review"; Figma's "Changed").
2. **A strict machine.** `in_review → approved` (approve), `in_review → changes_requested` (request changes), and `approved | changes_requested → in_review` (reopen). A decision is undone only by reopening, so a change of mind is two recorded steps, never a silent overwrite. Approve and request changes need a `ready` version; reopen does not (a decided version can later fail a re-check, ADR 0011). The table lives in `domain/reviews.py` and again as the `ck_review_events_transition` check; both are pinned by tests.
3. **Compare-and-set, 409 on conflict.** The request names `expected_state`; the domain refuses a stale one (`REVIEW_STATE_CONFLICT` with `current_state`), and the write is `UPDATE … WHERE review_state = :read AND review_revision = :read_revision [AND status = 'ready']`, so a decision made on a state that changed between read and write (including approve → reopen → approve, which a state-only check would miss) is refused too. No row lock is held across the request.
4. **Append-only history.** Every transition inserts a `review_events` row (who, when, from, to, an optional note ≤ 1,000 characters) numbered per version; the number equals the version's revision, so pages are keyset on `(version_id, sequence)` with no clock skew. A trigger refuses updates and direct deletes (only the cascade from deleting a version passes).
5. **Who may review.** One studio (ADR 0012): any signed-in user with the `write` scope may approve, request changes or reopen, their own uploads included; reading needs `read`. Decided in `domain/authorization.py` (`REVIEW_VERSIONS`, `READ_REVIEWS`). The note is optional for every action (GitHub requires one to request changes; Kiln's comments carry the detail instead).

## Consequences

- No self-approval guard, required reviewers or approval chains in v0.2; a later tenant or role model changes the policy only.
- The asset's state costs one extra indexed query per gallery page (`DISTINCT ON (asset_id)` over `uq_asset_versions_asset_id_number`), not a denormalised column that could drift.
- Clients must send the state they saw; a stale client gets a 409 it can explain, never a lost update.
- Truncating `review_events` is still possible for the database owner (tests clean up that way); the trigger guards the application path.

## Sources

[GitHub REST: create a review](https://docs.github.com/en/rest/pulls/reviews) (`APPROVE`, `REQUEST_CHANGES`, body required to request changes); [Frame.io status labels](https://blog.frame.io/2017/05/31/ios-version-1-4/); [Autodesk ShotGrid: tracking statuses](https://help.autodesk.com/cloudhelp/ENU/SG-Tutorials/files/SG_Tutorials_tu_tracking_statuses_html.html) (Version status starts at Pending Review); [Figma: Dev Mode statuses](https://help.figma.com/hc/en-us/articles/26781702258583-Dev-Mode-statuses-and-notifications) (Ready for dev, Completed, Changed); PostgreSQL 17 docs, `ALTER TABLE` (fast defaults, `NOT VALID`) and Read Committed re-evaluation of `UPDATE`; RFC 9457 section 3.2 (extension members).
