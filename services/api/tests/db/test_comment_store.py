"""Comment threads in Postgres: constraints, numbering under concurrency, locked resolution."""

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from db_fixtures import insert_user
from sqlalchemy import Engine, create_engine, insert, text
from sqlalchemy.exc import IntegrityError

from kiln_api.db.schema import comment_threads, comments
from kiln_api.domain.assets import UploadSpec, new_asset
from kiln_api.domain.comments import Region, new_thread
from kiln_api.domain.identity import Principal, User, session_principal
from kiln_api.domain.ids import uuid7
from kiln_api.enums import RegionShape
from kiln_api.repositories.assets import SqlAssetRepository
from kiln_api.repositories.unit_of_work import SqlUnitOfWork
from kiln_api.services.comments import CommentService

NOW = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
PARALLEL = 12


class _Clock:
    def now(self) -> datetime:
        return NOW


def _version(engine: Engine, user: User) -> Any:
    asset, version = new_asset(
        "Rock",
        UploadSpec(file_name="rock.png", content_type="image/png", size_bytes=10),
        now=NOW,
        new_id=uuid7,
        owner_id=user.id,
    )
    SqlAssetRepository(engine).add(asset, version)
    return version.id


def _thread_row(engine: Engine, user: User, **overrides: Any) -> None:
    values = {
        "id": uuid7(),
        "version_id": _version(engine, user),
        "number": 1,
        "author_id": user.id,
        "created_at": NOW,
        "updated_at": NOW,
        **overrides,
    }
    with engine.begin() as connection:
        connection.execute(insert(comment_threads).values(**values))


@pytest.mark.parametrize(
    "region",
    [
        {
            "region_shape": "rect",
            "region_x": 0.6,
            "region_y": 0,
            "region_width": 0.5,
            "region_height": 0.5,
        },
        {
            "region_shape": "rect",
            "region_x": 0,
            "region_y": 0,
            "region_width": 0,
            "region_height": 0.5,
        },
        {"region_shape": "rect", "region_x": 0, "region_y": 0},
        {"region_shape": "point", "region_x": 0.5, "region_y": 0.5, "region_width": 0.1},
        {"region_shape": "point", "region_x": 1.5, "region_y": 0.5},
        {"region_shape": "point", "region_x": float("nan"), "region_y": 0.5},
        {"region_shape": "circle", "region_x": 0.5, "region_y": 0.5},
        {"region_x": 0.5, "region_y": 0.5},  # coordinates without a shape
        {"number": 0},
        {"resolved_at": NOW},  # resolved by nobody
    ],
)
def test_the_database_refuses_regions_and_threads_that_break_the_rules(
    engine: Engine, user: User, region: dict[str, Any]
) -> None:
    with pytest.raises(IntegrityError):
        _thread_row(engine, user, **region)


def test_the_database_keeps_a_valid_rectangle_point_and_plain_thread(
    engine: Engine, user: User
) -> None:
    _thread_row(
        engine,
        user,
        region_shape="rect",
        region_x=0,
        region_y=0,
        region_width=1,
        region_height=1,
    )
    _thread_row(engine, user, region_shape="point", region_x=1, region_y=1)
    _thread_row(engine, user)


def _comment_row(engine: Engine, thread_id: Any, user: User, **overrides: Any) -> None:
    values = {
        "id": uuid7(),
        "thread_id": thread_id,
        "author_id": user.id,
        "body": "Hi",
        "is_root": False,
        "created_at": NOW,
        **overrides,
    }
    with engine.begin() as connection:
        connection.execute(insert(comments).values(**values))


@pytest.mark.parametrize(
    "overrides",
    [
        {"body": ""},
        {"body": "x" * 2001},
        {"body": "kept", "deleted_at": NOW},  # a deleted comment keeps no text
        {"is_root": True},  # a second root
    ],
)
def test_the_database_refuses_comments_that_break_the_rules(
    engine: Engine, user: User, overrides: dict[str, Any]
) -> None:
    thread_id = uuid7()
    _thread_row(engine, user, id=thread_id)
    _comment_row(engine, thread_id, user, is_root=True)

    with pytest.raises(IntegrityError):
        _comment_row(engine, thread_id, user, **overrides)


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


def test_parallel_threads_on_one_version_get_numbers_one_to_n(
    database_url: str, engine: Engine, user: User
) -> None:
    """Each caller on its own connection, released together: no number is taken twice."""
    version_id = _version(engine, user)
    principal: Principal = session_principal(user)
    own_engine = create_engine(database_url, pool_size=PARALLEL, max_overflow=0)
    service = CommentService(_Clock(), uuid7, SqlUnitOfWork(own_engine))

    errors = _in_parallel(
        lambda i: service.start_thread(principal, version_id, body=f"note {i}", region=None)
    )
    own_engine.dispose()

    assert errors == []
    with engine.connect() as connection:
        numbers = (
            connection.execute(
                text("SELECT number FROM comment_threads WHERE version_id = :v ORDER BY number"),
                {"v": version_id},
            )
            .scalars()
            .all()
        )
    assert numbers == list(range(1, PARALLEL + 1))


def test_without_the_number_lock_parallel_threads_collide(
    database_url: str, engine: Engine, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard above is what makes the test pass: with the lock removed, numbers collide."""
    from kiln_api.repositories import comments as module  # noqa: PLC0415 - patched for the test

    monkeypatch.setattr(module, "_NUMBER_LOCK", text("SELECT pg_sleep(0.05)"))
    version_id = _version(engine, user)
    principal = session_principal(user)
    own_engine = create_engine(database_url, pool_size=PARALLEL, max_overflow=0)
    service = CommentService(_Clock(), uuid7, SqlUnitOfWork(own_engine))

    errors = _in_parallel(
        lambda i: service.start_thread(principal, version_id, body=f"note {i}", region=None)
    )
    own_engine.dispose()

    assert any(isinstance(e, IntegrityError) for e in errors)


def test_two_people_resolving_at_once_keep_one_resolution(
    database_url: str, engine: Engine, user: User
) -> None:
    other = insert_user(engine, email="bob@kiln.test", display_name="Bob")
    version_id = _version(engine, user)
    own_engine = create_engine(database_url, pool_size=PARALLEL, max_overflow=0)
    service = CommentService(_Clock(), uuid7, SqlUnitOfWork(own_engine))
    thread = service.start_thread(
        session_principal(user),
        version_id,
        body="x",
        region=Region(shape=RegionShape.POINT, x=0.5, y=0.5),
    ).item.thread
    people = [session_principal(user), session_principal(other)]
    results: list[Any] = []

    errors = _in_parallel(
        lambda i: results.append(service.resolve(people[i % 2], thread.id, resolved=True))
    )
    own_engine.dispose()

    assert errors == []
    assert len({(r.thread.resolved_by, r.thread.resolved_at) for r in results}) == 1


def test_a_thread_id_from_the_domain_is_kept(engine: Engine, user: User) -> None:
    version_id = _version(engine, user)
    thread, root = new_thread(
        version_id, author_id=user.id, body="Hi", region=None, now=NOW, new_id=uuid7
    )

    with SqlUnitOfWork(engine)() as tx:
        stored = tx.comments.add_thread(thread, root)

    assert (stored.id, stored.number) == (thread.id, 1)
