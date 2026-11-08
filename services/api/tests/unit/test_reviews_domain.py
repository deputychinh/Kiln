"""The review state machine of KILN-11, pinned literally (a decision table, not derived)."""

from dataclasses import replace
from datetime import UTC, datetime
from itertools import product
from uuid import UUID, uuid4

import pytest

from kiln_api.domain.assets import AssetVersion
from kiln_api.domain.ids import uuid7
from kiln_api.domain.reviews import (
    REVIEW_TRANSITIONS,
    ReviewEvent,
    clean_review_note,
    decide,
    next_state,
)
from kiln_api.enums import ReviewAction, ReviewState, VersionStatus
from kiln_api.errors import (
    InvalidReviewNoteError,
    InvalidReviewTransitionError,
    ReviewStateConflictError,
    VersionNotReadyError,
)

NOW = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
ACTOR = uuid4()

IN_REVIEW = ReviewState.IN_REVIEW
APPROVED = ReviewState.APPROVED
CHANGES = ReviewState.CHANGES_REQUESTED
APPROVE = ReviewAction.APPROVE
REQUEST = ReviewAction.REQUEST_CHANGES
REOPEN = ReviewAction.REOPEN

# Every (state, action) pair and its outcome: the next state, or None for "refused".
DECISION_TABLE: list[tuple[ReviewState, ReviewAction, ReviewState | None]] = [
    (IN_REVIEW, APPROVE, APPROVED),
    (IN_REVIEW, REQUEST, CHANGES),
    (IN_REVIEW, REOPEN, None),
    (APPROVED, APPROVE, None),
    (APPROVED, REQUEST, None),
    (APPROVED, REOPEN, IN_REVIEW),
    (CHANGES, APPROVE, None),
    (CHANGES, REQUEST, None),
    (CHANGES, REOPEN, IN_REVIEW),
]


def _version(
    state: ReviewState = IN_REVIEW,
    *,
    status: VersionStatus = VersionStatus.READY,
    revision: int = 0,
) -> AssetVersion:
    return AssetVersion(
        id=uuid4(),
        asset_id=uuid4(),
        number=1,
        status=status,
        file_name="rock.png",
        content_type="image/png",
        size_bytes=10,
        object_key="assets/a/v.png",
        created_at=NOW,
        updated_at=NOW,
        review_state=state,
        review_revision=revision,
    )


def _decide(
    version: AssetVersion,
    action: ReviewAction,
    *,
    expected_state: ReviewState | None = None,
    expected_revision: int | None = None,
    note: str | None = None,
) -> tuple[AssetVersion, ReviewEvent]:
    return decide(
        version,
        action,
        expected_state=version.review_state if expected_state is None else expected_state,
        expected_revision=expected_revision,
        actor_id=ACTOR,
        note=note,
        now=NOW,
        new_id=uuid7,
    )


def test_the_decision_table_covers_every_state_and_action_once() -> None:
    assert {(state, action) for state, action, _ in DECISION_TABLE} == set(
        product(ReviewState, ReviewAction)
    )
    assert len(DECISION_TABLE) == len(ReviewState) * len(ReviewAction)


def test_the_transition_table_is_exactly_the_decision_table() -> None:
    allowed = {(state, action): to for state, action, to in DECISION_TABLE if to is not None}

    assert dict(REVIEW_TRANSITIONS) == allowed


@pytest.mark.parametrize(("state", "action", "expected"), DECISION_TABLE)
def test_each_state_and_action_leads_where_the_table_says(
    state: ReviewState, action: ReviewAction, expected: ReviewState | None
) -> None:
    version = _version(state, revision=4)

    if expected is None:
        with pytest.raises(InvalidReviewTransitionError) as refused:
            _decide(version, action)
        assert refused.value.extensions == {"current_state": state.value}
        return
    decided, event = _decide(version, action)

    assert next_state(state, action) is expected
    assert decided.review_state is expected
    assert decided.review_revision == 5
    assert event.from_state is state
    assert event.to_state is expected
    assert event.sequence == 5
    assert event.action is action
    assert event.actor_id == ACTOR
    assert event.version_id == version.id
    assert event.created_at == NOW


@pytest.mark.parametrize(
    ("state", "action", "seen"),
    [
        (state, action, seen)
        for state, action, seen in product(ReviewState, ReviewAction, ReviewState)
        if seen is not state
    ],
)
def test_a_reviewer_who_saw_another_state_is_told_the_current_one(
    state: ReviewState, action: ReviewAction, seen: ReviewState
) -> None:
    with pytest.raises(ReviewStateConflictError) as conflict:
        _decide(_version(state), action, expected_state=seen)

    assert conflict.value.current is state
    assert conflict.value.extensions == {"current_state": state.value, "current_revision": 0}


@pytest.mark.parametrize(
    "status", [VersionStatus.PENDING_UPLOAD, VersionStatus.PROCESSING, VersionStatus.FAILED]
)
@pytest.mark.parametrize("action", [APPROVE, REQUEST])
def test_a_decision_needs_a_ready_version(status: VersionStatus, action: ReviewAction) -> None:
    with pytest.raises(VersionNotReadyError):
        _decide(_version(status=status), action)


@pytest.mark.parametrize("status", list(VersionStatus))
@pytest.mark.parametrize("state", [APPROVED, CHANGES])
def test_a_decided_version_can_be_reopened_whatever_its_processing_status(
    status: VersionStatus, state: ReviewState
) -> None:
    decided, _ = _decide(_version(state, status=status), REOPEN)

    assert decided.review_state is IN_REVIEW


def test_a_conflict_is_reported_before_the_table_and_the_ready_rule() -> None:
    """A stale reviewer is told the state changed, not that their action is invalid now."""
    with pytest.raises(ReviewStateConflictError):
        _decide(_version(APPROVED, status=VersionStatus.FAILED), APPROVE, expected_state=IN_REVIEW)


def test_a_decision_leaves_everything_else_of_the_version_alone() -> None:
    version = _version()

    decided, _ = _decide(version, APPROVE)

    assert decided == replace(version, review_state=APPROVED, review_revision=1)


def test_each_event_gets_a_new_id() -> None:
    ids: list[UUID] = [_decide(_version(), APPROVE)[1].id for _ in range(3)]

    assert len(set(ids)) == 3


# --- notes -------------------------------------------------------------------------------------


@pytest.mark.parametrize("raw", [None, "", "   ", "\r\n\t "])
def test_no_note_or_a_blank_one_is_no_note(raw: str | None) -> None:
    assert clean_review_note(raw) is None


def test_a_note_is_trimmed_and_its_line_breaks_unified() -> None:
    assert clean_review_note("  Rim is fixed.\r\nGood to go.\r ") == "Rim is fixed.\nGood to go."


def test_a_note_of_1000_characters_is_kept_and_1001_refused() -> None:
    assert clean_review_note("a" * 1000) == "a" * 1000
    with pytest.raises(InvalidReviewNoteError):
        clean_review_note("a" * 1001)


@pytest.mark.parametrize(
    "note",
    [
        "ok\x00",  # NUL
        "ok\x07",  # BEL
        "ok\u200b",  # zero-width space
        "ok\u202e",  # right-to-left override
        "ok\U000e0041",  # tag character
        "\u3164",  # Hangul filler only
        "o\u2028k",  # line separator (inside: trimming drops it at the ends)
    ],
)
def test_a_note_with_hidden_or_control_characters_is_refused(note: str) -> None:
    with pytest.raises(InvalidReviewNoteError):
        clean_review_note(note)


@pytest.mark.parametrize(
    "note",
    [
        "Đã sửa viền, duyệt.",
        "تمت الموافقة",
        "स्वीकृत",
        "می‌خواهم",  # Persian with ZWNJ
        "👩‍🎨 approved",  # emoji ZWJ sequence
        "承認しました",
    ],
)
def test_a_note_in_any_script_is_kept(note: str) -> None:
    assert clean_review_note(note) == note


def test_the_note_goes_through_the_note_rules_in_a_decision() -> None:
    _, event = _decide(_version(), REQUEST, note="  Darken the rim.  ")
    assert event.note == "Darken the rim."
    with pytest.raises(InvalidReviewNoteError):
        _decide(_version(), REQUEST, note="x\u200b")


# --- review round 1: the revision the reviewer saw (ADR 0016) ------------------------------------


@pytest.mark.parametrize("seen", [0, 1, 3, 100])
def test_a_reviewer_who_saw_another_revision_of_the_same_state_is_refused(seen: int) -> None:
    """Approve then reopen leaves the state as it was: only the revision tells them apart."""
    with pytest.raises(ReviewStateConflictError) as conflict:
        _decide(_version(IN_REVIEW, revision=2), APPROVE, expected_revision=seen)

    assert conflict.value.extensions == {"current_state": "in_review", "current_revision": 2}


def test_the_current_revision_or_none_lets_the_decision_through() -> None:
    for expected in (2, None):
        decided, event = _decide(
            _version(IN_REVIEW, revision=2), APPROVE, expected_revision=expected
        )
        assert (decided.review_revision, event.sequence) == (3, 3)
