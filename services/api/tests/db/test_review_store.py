"""Review states and history in Postgres (KILN-11): compare-and-set under real concurrency,
an append-only history, and the transition table as a database check."""

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from db_fixtures import dml_role_name, insert_user
from sqlalchemy import Connection, Engine, create_engine, insert, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from kiln_api.db.schema import review_events
from kiln_api.domain.assets import UploadSpec, new_asset, new_version
from kiln_api.domain.identity import User, session_principal
from kiln_api.domain.ids import uuid7
from kiln_api.domain.reviews import decide
from kiln_api.enums import ReviewAction, ReviewState
from kiln_api.errors import ReviewStateConflictError, VersionNotReadyError
from kiln_api.repositories.assets import SqlAssetRepository
from kiln_api.repositories.reviews import SqlReviewStore
from kiln_api.repositories.unit_of_work import SqlUnitOfWork
from kiln_api.services.reviews import ReviewService

NOW = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
PARALLEL = 12
IN_REVIEW = ReviewState.IN_REVIEW


class _Clock:
    def now(self) -> datetime:
        return NOW


def _ready_version(engine: Engine, user: User, name: str = "Rock") -> UUID:
    asset, version = new_asset(
        name,
        UploadSpec(file_name="rock.png", content_type="image/png", size_bytes=10),
        now=NOW,
        new_id=uuid7,
        owner_id=user.id,
    )
    SqlAssetRepository(engine).add(asset, version)
    _set_status(engine, version.id, "ready")
    return version.id


def _set_status(engine: Engine, version_id: UUID, status: str) -> None:
    reason = "'UNREADABLE_IMAGE'" if status == "failed" else "NULL"
    with engine.begin() as connection:
        connection.execute(
            text(
                f"UPDATE asset_versions SET status = :s, failure_reason = {reason} WHERE id = :v"  # noqa: S608 - a literal of this test
            ),
            {"s": status, "v": version_id},
        )


def _service(engine: Engine) -> ReviewService:
    return ReviewService(_Clock(), uuid7, SqlUnitOfWork(engine))


def _state(engine: Engine, version_id: UUID) -> tuple[str, int, int]:
    """The version's state and revision, and how many events it has."""
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT review_state, review_revision,"
                " (SELECT count(*) FROM review_events WHERE version_id = v.id) AS events"
                " FROM asset_versions v WHERE id = :v"
            ),
            {"v": version_id},
        ).one()
    return row.review_state, row.review_revision, row.events


def _in_parallel(work: Callable[[int], object], count: int = PARALLEL) -> list[BaseException]:
    barrier = threading.Barrier(count)
    errors: list[BaseException] = []

    def run(index: int) -> None:
        try:
            barrier.wait()
            work(index)
        except BaseException as error:  # collected and asserted by the test
            errors.append(error)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return errors


def _wait_until_blocked(engine: Engine) -> None:
    """Return once some backend waits for a lock while updating the version's review state."""
    deadline = time.monotonic() + 20
    with engine.connect() as watcher:
        while time.monotonic() < deadline:
            waiting = watcher.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'"
                    " AND query LIKE 'UPDATE asset_versions SET review_state%'"
                    " AND datname = current_database()"
                )
            ).scalar_one()
            if waiting:
                return
            watcher.rollback()
            time.sleep(0.02)
    pytest.fail("the second reviewer never waited for the first one's row lock")


# --- compare-and-set ---------------------------------------------------------------------------


def test_a_second_reviewer_waiting_on_the_first_gets_a_conflict_not_a_second_decision(
    database_url: str, engine: Engine, user: User
) -> None:
    """Deterministic interleaving: A has written and holds its transaction open; B reads the old
    committed state, passes the domain check, and its UPDATE waits on A's row lock. A commits:
    Postgres re-checks B's guard on the new row, which no longer matches, so B is refused."""
    other = insert_user(engine, email="bob@kiln.test", display_name="Bob")
    version_id = _ready_version(engine, user)
    reader = SqlAssetRepository(engine)
    read = reader.get_version(version_id)
    decided, event = decide(
        read,
        ReviewAction.APPROVE,
        expected_state=IN_REVIEW,
        actor_id=user.id,
        note=None,
        now=NOW,
        new_id=uuid7,
    )
    own_engine = create_engine(database_url, pool_size=2, max_overflow=0)
    outcome: list[BaseException | object] = []

    def second_reviewer() -> None:
        try:
            outcome.append(
                _service(own_engine).transition(
                    session_principal(other),
                    version_id,
                    action=ReviewAction.REQUEST_CHANGES,
                    expected_state=IN_REVIEW,
                    note="No.",
                )
            )
        except BaseException as error:  # asserted below
            outcome.append(error)

    with engine.connect() as first:
        SqlReviewStore(first).record(read, decided, event)  # written, not committed
        thread = threading.Thread(target=second_reviewer)
        thread.start()
        _wait_until_blocked(engine)
        first.commit()
    thread.join(timeout=30)
    own_engine.dispose()

    assert len(outcome) == 1
    assert isinstance(outcome[0], ReviewStateConflictError)
    assert outcome[0].current is ReviewState.APPROVED
    assert _state(engine, version_id) == ("approved", 1, 1)


def test_twelve_reviewers_at_once_make_exactly_one_decision(
    database_url: str, engine: Engine, user: User
) -> None:
    """Each on its own connection behind a barrier; half approve, half request changes."""
    version_id = _ready_version(engine, user)
    own_engine = create_engine(database_url, pool_size=PARALLEL, max_overflow=0)
    service = _service(own_engine)
    actions = [ReviewAction.APPROVE, ReviewAction.REQUEST_CHANGES]

    errors = _in_parallel(
        lambda i: service.transition(
            session_principal(user),
            version_id,
            action=actions[i % 2],
            expected_state=IN_REVIEW,
            note=None,
        )
    )
    own_engine.dispose()

    assert len(errors) == PARALLEL - 1
    assert all(isinstance(error, ReviewStateConflictError) for error in errors)
    state, revision, events = _state(engine, version_id)
    assert state in {"approved", "changes_requested"}
    assert (revision, events) == (1, 1)


def test_a_reviewer_who_read_before_a_reopen_and_a_new_decision_is_refused(
    engine: Engine, user: User
) -> None:
    """Same state, newer revision (approved, reopened, approved again): the revision guards it."""
    version_id = _ready_version(engine, user)
    stale = SqlAssetRepository(engine).get_version(version_id)
    service = _service(engine)
    principal = session_principal(user)
    for action, expected in [
        (ReviewAction.APPROVE, IN_REVIEW),
        (ReviewAction.REOPEN, ReviewState.APPROVED),
    ]:
        service.transition(principal, version_id, action=action, expected_state=expected, note=None)
    decided, event = decide(
        stale,
        ReviewAction.REQUEST_CHANGES,
        expected_state=IN_REVIEW,
        actor_id=user.id,
        note=None,
        now=NOW,
        new_id=uuid7,
    )

    with engine.connect() as connection, pytest.raises(ReviewStateConflictError) as refused:
        SqlReviewStore(connection).record(stale, decided, event)

    assert refused.value.current is IN_REVIEW
    assert _state(engine, version_id) == ("in_review", 2, 2)


def test_a_decision_on_a_version_that_failed_meanwhile_is_refused(
    engine: Engine, user: User
) -> None:
    """The guarded write re-checks `ready`: a worker re-check may fail it after the read."""
    version_id = _ready_version(engine, user)
    read = SqlAssetRepository(engine).get_version(version_id)
    decided, event = decide(
        read,
        ReviewAction.APPROVE,
        expected_state=IN_REVIEW,
        actor_id=user.id,
        note=None,
        now=NOW,
        new_id=uuid7,
    )
    _set_status(engine, version_id, "failed")

    with engine.connect() as connection, pytest.raises(VersionNotReadyError):
        SqlReviewStore(connection).record(read, decided, event)

    assert _state(engine, version_id) == ("in_review", 0, 0)


# --- the history is append-only ------------------------------------------------------------------


def _one_event(engine: Engine, user: User) -> UUID:
    version_id = _ready_version(engine, user)
    _service(engine).transition(
        session_principal(user),
        version_id,
        action=ReviewAction.APPROVE,
        expected_state=IN_REVIEW,
        note="Looks right.",
    )
    return version_id


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE review_events SET note = 'rewritten'",
        "UPDATE review_events SET to_state = 'approved'",
        "DELETE FROM review_events",
    ],
)
def test_the_database_refuses_to_change_or_delete_an_event(
    engine: Engine, user: User, statement: str
) -> None:
    version_id = _one_event(engine, user)

    with engine.begin() as connection, pytest.raises(DBAPIError, match="append-only"):
        connection.execute(text(statement))

    assert _state(engine, version_id) == ("approved", 1, 1)


def test_a_delete_from_another_trigger_is_refused_while_the_version_exists(
    engine: Engine, user: User
) -> None:
    """Only the cascade of a deleted version may remove events, not any nested trigger (0012)."""
    version_id = _one_event(engine, user)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE FUNCTION pg_temp.sneaky_delete() RETURNS trigger LANGUAGE plpgsql AS $$"
                " BEGIN DELETE FROM review_events; RETURN NEW; END $$"
            )
        )
        connection.execute(
            text(
                "CREATE TRIGGER sneaky_delete AFTER INSERT ON maintenance_runs"
                " FOR EACH ROW EXECUTE FUNCTION pg_temp.sneaky_delete()"
            )
        )
    try:
        with engine.begin() as connection, pytest.raises(DBAPIError, match="append-only"):
            connection.execute(text("INSERT INTO maintenance_runs VALUES ('sneaky', now())"))
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP TRIGGER sneaky_delete ON maintenance_runs"))

    assert _state(engine, version_id) == ("approved", 1, 1)


@pytest.mark.parametrize(
    "statement",
    [
        "TRUNCATE review_events",
        "TRUNCATE review_events RESTART IDENTITY CASCADE",
        "TRUNCATE assets CASCADE",  # reaches the history through the foreign keys
    ],
)
def test_the_database_refuses_to_truncate_the_history(
    engine: Engine, user: User, statement: str
) -> None:
    """Row triggers never see TRUNCATE; the statement-level guard does (KILN-51, ADR 0018)."""
    version_id = _one_event(engine, user)

    with engine.begin() as connection, pytest.raises(DBAPIError, match="append-only"):
        connection.execute(text(statement))

    assert _state(engine, version_id) == ("approved", 1, 1)


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE review_events SET note = 'rewritten'",
        "DELETE FROM review_events",
        "TRUNCATE review_events",
    ],
)
def test_replica_mode_does_not_turn_the_history_guards_off(
    engine: Engine, user: User, statement: str
) -> None:
    """`session_replication_role = replica` skips ordinary triggers; ours fire ALWAYS (0014)."""
    version_id = _one_event(engine, user)

    with engine.begin() as connection:
        connection.execute(text("SET LOCAL session_replication_role = replica"))
        with pytest.raises(DBAPIError, match="append-only"):
            connection.execute(text(statement))

    assert _state(engine, version_id) == ("approved", 1, 1)


def test_the_truncate_guard_is_a_statement_level_before_trigger(engine: Engine) -> None:
    with engine.connect() as connection:
        definition = connection.execute(
            text(
                "SELECT pg_get_triggerdef(oid) FROM pg_trigger"
                " WHERE tgrelid = 'review_events'::regclass"
                " AND tgname = 'review_events_no_truncate'"
            )
        ).scalar_one()

    assert definition == (
        "CREATE TRIGGER review_events_no_truncate BEFORE TRUNCATE ON public.review_events"
        " FOR EACH STATEMENT EXECUTE FUNCTION review_events_append_only()"
    )


def test_deleting_an_asset_deletes_its_versions_history_with_them(
    engine: Engine, user: User
) -> None:
    version_id = _one_event(engine, user)

    with engine.begin() as connection:
        connection.execute(
            text(
                "DELETE FROM assets WHERE id = (SELECT asset_id FROM asset_versions WHERE id = :v)"
            ),
            {"v": version_id},
        )
        left = connection.execute(select(review_events)).all()

    assert left == []


@contextmanager
def _dml_role_on(engine: Engine) -> Iterator[str]:
    """A role with only SELECT, INSERT, UPDATE and DELETE on this database's tables, as the app's
    login will have once the owner and runtime roles are split (KILN-58). Roles are shared by the
    cluster, so the name carries the database's (`dml_role_name`): suites running in parallel
    against their own test databases never share one. Dropped afterwards, also when the test fails
    (KILN-62): `DROP OWNED BY` revokes its grants here, then `DROP ROLE` removes it."""
    with engine.begin() as connection:
        database = connection.execute(text("SELECT current_database()")).scalar_one()
        role = dml_role_name(database)
        quoted = connection.dialect.identifier_preparer.quote_identifier(role)
        if not _role_exists(connection, role):  # left by a run that was killed: reuse, then drop
            connection.execute(text(f"CREATE ROLE {quoted} NOLOGIN"))
        connection.execute(
            text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {quoted}")
        )
    try:
        yield role
    finally:
        with engine.begin() as connection:
            connection.execute(text(f"DROP OWNED BY {quoted}"))
            connection.execute(text(f"DROP ROLE {quoted}"))


def _role_exists(connection: Connection, role: str) -> bool:
    found = connection.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": role})
    return found.first() is not None


@pytest.fixture
def dml_role(engine: Engine) -> Iterator[str]:
    with _dml_role_on(engine) as role:
        yield role


def test_the_dml_role_is_named_for_its_database_and_dropped_after_use(engine: Engine) -> None:
    """KILN-62: the fixture used to leave its cluster-wide role behind after every run."""
    with engine.connect() as connection:
        database = connection.execute(text("SELECT current_database()")).scalar_one()

    with _dml_role_on(engine) as role, engine.connect() as connection:
        existed = _role_exists(connection, role)
    with engine.connect() as connection:
        left = _role_exists(connection, role)

    assert role == f"{database}_dml"
    assert (existed, left) == (True, False)


def test_the_dml_role_is_dropped_when_the_test_using_it_fails(engine: Engine) -> None:
    used: list[str] = []

    def failing_test() -> None:
        with _dml_role_on(engine) as role:
            used.append(role)
            raise RuntimeError("the test failed")

    with pytest.raises(RuntimeError, match="the test failed"):
        failing_test()

    with engine.connect() as connection:
        assert used
        assert not _role_exists(connection, used[0])


def test_a_dml_role_left_by_a_killed_run_is_reused_and_then_dropped(engine: Engine) -> None:
    with engine.begin() as connection:
        database = connection.execute(text("SELECT current_database()")).scalar_one()
        connection.execute(text(f'CREATE ROLE "{dml_role_name(database)}" NOLOGIN'))

    with _dml_role_on(engine) as role:
        pass

    with engine.connect() as connection:
        assert not _role_exists(connection, role)


def test_a_dml_role_cannot_shadow_the_versions_table_to_erase_a_live_history(
    engine: Engine, user: User, dml_role: str
) -> None:
    """KILN-51 round 3: a temporary `asset_versions` used to make a live version look gone to the
    append-only check, so a direct DELETE passed (migration 0016, ADR 0023)."""
    version_id = _one_event(engine, user)

    with engine.begin() as connection:
        connection.execute(text(f'SET LOCAL ROLE "{dml_role}"'))
        connection.execute(text("CREATE TEMP TABLE asset_versions (id uuid) ON COMMIT DROP"))
        with pytest.raises(DBAPIError, match="append-only"):
            connection.execute(text("DELETE FROM review_events"))

    assert _state(engine, version_id) == ("approved", 1, 1)


def test_a_dml_role_still_removes_the_history_of_a_version_it_deletes(
    engine: Engine, user: User, dml_role: str
) -> None:
    version_id = _one_event(engine, user)

    with engine.begin() as connection:
        connection.execute(text(f'SET LOCAL ROLE "{dml_role}"'))
        connection.execute(text("DELETE FROM asset_versions WHERE id = :v"), {"v": version_id})
        left = connection.execute(select(review_events)).all()

    assert left == []


def test_an_event_orphaned_in_replica_mode_can_be_cleaned_up_afterwards(
    engine: Engine, user: User
) -> None:
    """Replica mode skips the foreign key's cascade, so deleting a version leaves its events;
    once the version is gone they may be deleted directly (migration 0015, ADR 0022)."""
    version_id = _one_event(engine, user)
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL session_replication_role = replica"))
        connection.execute(text("DELETE FROM asset_versions WHERE id = :v"), {"v": version_id})
    orphans = text("SELECT count(*) FROM review_events WHERE version_id = :v")
    with engine.connect() as connection:
        left_behind = connection.execute(orphans, {"v": version_id}).scalar_one()

    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM review_events WHERE version_id = :v"), {"v": version_id}
        )
        after_cleanup = connection.execute(orphans, {"v": version_id}).scalar_one()

    assert (left_behind, after_cleanup) == (1, 0)


def test_deleting_a_version_deletes_its_history_with_it(engine: Engine, user: User) -> None:
    version_id = _one_event(engine, user)

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM asset_versions WHERE id = :v"), {"v": version_id})
        left = connection.execute(select(review_events)).all()

    assert left == []


def _event_row(engine: Engine, user: User, **overrides: Any) -> None:
    values = {
        "id": uuid7(),
        "version_id": _ready_version(engine, user, name=f"Rock {uuid7()}"),
        "sequence": 1,
        "action": "approve",
        "from_state": "in_review",
        "to_state": "approved",
        "actor_id": user.id,
        "note": None,
        "created_at": NOW,
        **overrides,
    }
    with engine.begin() as connection:
        connection.execute(insert(review_events).values(**values))


@pytest.mark.parametrize(
    "overrides",
    [
        {"to_state": "changes_requested"},  # approve must lead to approved
        {"from_state": "approved", "to_state": "approved"},  # approve twice
        {"action": "reopen", "from_state": "in_review", "to_state": "in_review"},
        {"action": "reopen", "from_state": "approved", "to_state": "changes_requested"},
        {"action": "request_changes", "from_state": "approved", "to_state": "changes_requested"},
        {"action": "merge"},
        {"from_state": "rejected"},
        {"sequence": 0},
        {"note": ""},
        {"note": "a" * 1001},
    ],
)
def test_the_database_refuses_events_that_break_the_rules(
    engine: Engine, user: User, overrides: dict[str, Any]
) -> None:
    with pytest.raises(IntegrityError):
        _event_row(engine, user, **overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"action": "request_changes", "to_state": "changes_requested"},
        {"action": "reopen", "from_state": "approved", "to_state": "in_review"},
        {"action": "reopen", "from_state": "changes_requested", "to_state": "in_review"},
        {"note": "a" * 1000},
    ],
)
def test_the_database_keeps_each_allowed_transition(
    engine: Engine, user: User, overrides: dict[str, Any]
) -> None:
    _event_row(engine, user, **overrides)


def test_one_sequence_number_per_version(engine: Engine, user: User) -> None:
    version_id = _one_event(engine, user)

    with pytest.raises(IntegrityError):
        _event_row(engine, user, version_id=version_id)


@pytest.mark.parametrize("state", ["rejected", "", "APPROVED"])
def test_the_database_refuses_an_unknown_version_state(
    engine: Engine, user: User, state: str
) -> None:
    version_id = _ready_version(engine, user)

    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(
            text("UPDATE asset_versions SET review_state = :s WHERE id = :v"),
            {"s": state, "v": version_id},
        )


# --- reading -----------------------------------------------------------------------------------


def test_an_asset_takes_the_review_state_of_its_newest_version(engine: Engine, user: User) -> None:
    repository = SqlAssetRepository(engine)
    first = _ready_version(engine, user)
    asset_id = repository.get_version(first).asset_id
    other_asset = repository.get_version(_ready_version(engine, user, name="Crate")).asset_id
    service = _service(engine)
    principal = session_principal(user)
    service.transition(
        principal, first, action=ReviewAction.APPROVE, expected_state=IN_REVIEW, note=None
    )
    assert repository.newest_review_states([asset_id, other_asset]) == {
        asset_id: ReviewState.APPROVED,
        other_asset: IN_REVIEW,
    }

    second = repository.add_next_version(
        asset_id,
        lambda asset, number: new_version(
            asset,
            number,
            UploadSpec(file_name="rock2.png", content_type="image/png", size_bytes=10),
            now=NOW,
            new_id=uuid7,
        ),
    )

    assert repository.newest_review_states([asset_id]) == {asset_id: IN_REVIEW}
    assert repository.get_version(first).review_state is ReviewState.APPROVED
    assert second.review_state is IN_REVIEW
    assert repository.newest_review_states([]) == {}
