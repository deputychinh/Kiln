import argparse
import time
import uuid

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, create_engine, inspect, make_url, text
from sqlalchemy.exc import OperationalError

from kiln_api.db.schema import metadata


def test_the_migrations_match_the_schema_module(database_url: str) -> None:
    engine = create_engine(database_url)
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), metadata)
    engine.dispose()

    assert diff == []


def test_the_first_migration_downgrades_and_upgrades_cleanly(
    database_url: str, alembic_config: Config
) -> None:
    config = alembic_config
    engine = create_engine(database_url)

    command.downgrade(config, "base")
    tables_after_downgrade = set(inspect(engine).get_table_names())
    command.upgrade(config, "head")
    tables_after_upgrade = set(inspect(engine).get_table_names())
    engine.dispose()

    assert tables_after_downgrade == {"alembic_version"}
    assert {"assets", "asset_versions"} <= tables_after_upgrade


def test_constraints_keep_the_names_from_the_naming_convention(database_url: str) -> None:
    engine = create_engine(database_url)
    inspector = inspect(engine)
    checks = {c["name"] for c in inspector.get_check_constraints("asset_versions")}
    indexes = {i["name"] for i in inspector.get_indexes("assets")}
    engine.dispose()

    assert checks == {
        "ck_asset_versions_number_positive",
        "ck_asset_versions_status",
        "ck_asset_versions_file_name_length",
        "ck_asset_versions_size_range",
        "ck_asset_versions_failure_reason",
        "ck_asset_versions_failure_reason_when_failed",
        "ck_asset_versions_review_state",
        "ck_asset_versions_review_revision_non_negative",
    }
    assert "ix_assets_created_at_id" in indexes


_DEFINITIONS = text(
    """
    SELECT rel.relname || '.' || con.conname AS name, pg_get_constraintdef(con.oid) AS definition
    FROM pg_constraint con JOIN pg_class rel ON rel.oid = con.conrelid
    JOIN pg_namespace ns ON ns.oid = rel.relnamespace
    WHERE ns.nspname = 'public' AND rel.relname <> 'alembic_version'
    UNION ALL
    SELECT tablename || '.' || indexname, indexdef FROM pg_indexes
    WHERE schemaname = 'public' AND tablename <> 'alembic_version'
    """
)


def _definitions(engine: Engine) -> dict[str, str]:
    with engine.connect() as connection:
        return {row.name: row.definition for row in connection.execute(_DEFINITIONS)}


def test_constraint_and_index_definitions_match_the_schema_module(database_url: str) -> None:
    """Alembic does not compare CHECK texts, so compare what Postgres stores for both."""
    url = make_url(database_url)
    reference_name = f"kiln_schema_{uuid.uuid4().hex[:8]}_test"
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{reference_name}" WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE "{reference_name}"'))
    reference = create_engine(url.set(database=reference_name))
    metadata.create_all(reference)
    migrated = create_engine(database_url)

    try:
        assert _definitions(migrated) == _definitions(reference)
    finally:
        reference.dispose()
        migrated.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{reference_name}" WITH (FORCE)'))
        admin.dispose()


def test_migration_0003_backfills_existing_rows(database_url: str, alembic_config: Config) -> None:
    engine = create_engine(database_url)
    command.downgrade(alembic_config, "0002_idempotency_keys")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO assets (id, name, kind, created_at, updated_at)"
                " VALUES ('00000000-0000-7000-8000-000000000001', 'Old', 'image', now(), now())"
            )
        )
        for number, status in ((1, "failed"), (2, "processing")):
            connection.execute(
                text(
                    "INSERT INTO asset_versions (id, asset_id, number, status, file_name,"
                    " content_type, size_bytes, object_key, created_at, updated_at) VALUES"
                    " (:id, '00000000-0000-7000-8000-000000000001', :n, :s, 'a.png', 'image/png',"
                    " 1, :key, now(), now())"
                ),
                {
                    "id": f"00000000-0000-7000-8000-00000000001{number}",
                    "n": number,
                    "s": status,
                    "key": f"assets/old/v{number}",
                },
            )

    command.upgrade(alembic_config, "head")

    with engine.connect() as connection:
        reasons: dict[str, str | None] = dict(
            connection.execute(text("SELECT status, failure_reason FROM asset_versions")).all()
        )
        queued = connection.execute(text("SELECT count(*) FROM jobs")).scalar_one()
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM jobs"))
        connection.execute(text("DELETE FROM asset_versions"))
        connection.execute(text("DELETE FROM assets"))
    engine.dispose()

    assert reasons == {"failed": "PROCESSING_GAVE_UP", "processing": None}
    assert queued == 1


def test_migration_0004_downgrade_maps_expired_uploads_to_a_reason_the_old_check_allows(
    database_url: str, alembic_config: Config
) -> None:
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO assets (id, name, kind, created_at, updated_at)"
                " VALUES ('00000000-0000-7000-8000-000000000004', 'Gone', 'image', now(), now())"
            )
        )
        connection.execute(
            text(
                "INSERT INTO asset_versions (id, asset_id, number, status, failure_reason,"
                " file_name, content_type, size_bytes, object_key, created_at, updated_at) VALUES"
                " ('00000000-0000-7000-8000-000000000041', '00000000-0000-7000-8000-000000000004',"
                " 1, 'failed', 'UPLOAD_EXPIRED', 'a.png', 'image/png', 1, 'assets/gone/v1',"
                " now(), now())"
            )
        )
        connection.execute(
            text("INSERT INTO maintenance_runs (task, last_started_at) VALUES ('cleanup', now())")
        )

    command.downgrade(alembic_config, "0003_jobs_and_processing")
    with engine.connect() as connection:
        reason = connection.execute(text("SELECT failure_reason FROM asset_versions")).scalar_one()
        tables = inspect(connection).get_table_names()
    command.upgrade(alembic_config, "head")
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM asset_versions"))
        connection.execute(text("DELETE FROM assets"))
    engine.dispose()

    assert reason == "PROCESSING_GAVE_UP"
    assert "maintenance_runs" not in tables


def test_migration_0005_sends_ready_models_back_for_a_preview(
    database_url: str, alembic_config: Config
) -> None:
    engine = create_engine(database_url)
    command.downgrade(alembic_config, "0004_maintenance")
    with engine.begin() as connection:
        for asset, kind, version, extension in (
            (
                "00000000-0000-7000-8000-000000000051",
                "model",
                "00000000-0000-7000-8000-0000000005a1",
                "glb",
            ),
            (
                "00000000-0000-7000-8000-000000000052",
                "image",
                "00000000-0000-7000-8000-0000000005a2",
                "png",
            ),
        ):
            connection.execute(
                text(
                    "INSERT INTO assets (id, name, kind, created_at, updated_at)"
                    " VALUES (:id, 'A', :kind, now(), now())"
                ),
                {"id": asset, "kind": kind},
            )
            connection.execute(
                text(
                    "INSERT INTO asset_versions (id, asset_id, number, status, file_name,"
                    " content_type, size_bytes, object_key, created_at, updated_at) VALUES"
                    " (:id, :asset, 1, 'ready', 'a', 'x', 1, :key, now(), now())"
                ),
                {"id": version, "asset": asset, "key": f"assets/{asset}/v1.{extension}"},
            )
            connection.execute(
                text(
                    "INSERT INTO jobs (id, kind, version_id, status, attempts, run_after,"
                    " created_at, updated_at) VALUES"
                    " (gen_random_uuid(), 'thumbnail', :v, 'done', 1, now(), now(), now())"
                ),
                {"v": version},
            )

    with engine.begin() as connection:  # covers set by the old worker; a third model is running
        connection.execute(
            text(
                "UPDATE assets SET cover_version_id = '00000000-0000-7000-8000-0000000005a1'"
                " WHERE id = '00000000-0000-7000-8000-000000000051'"
            )
        )
        connection.execute(
            text(
                "INSERT INTO assets (id, name, kind, created_at, updated_at)"
                " VALUES ('00000000-0000-7000-8000-000000000054', 'R', 'model', now(), now())"
            )
        )
        connection.execute(
            text(
                "INSERT INTO asset_versions (id, asset_id, number, status, file_name,"
                " content_type, size_bytes, object_key, created_at, updated_at) VALUES"
                " ('00000000-0000-7000-8000-0000000005a4', '00000000-0000-7000-8000-000000000054',"
                " 1, 'processing', 'r', 'x', 1, 'assets/r/v1.glb', now(), now())"
            )
        )
        connection.execute(
            text(
                "INSERT INTO jobs (id, kind, version_id, status, attempts, run_after,"
                " leased_until, created_at, updated_at) VALUES (gen_random_uuid(), 'thumbnail',"
                " '00000000-0000-7000-8000-0000000005a4', 'running', 1, now(),"
                " now() + interval '5 minutes', now(), now())"
            )
        )

    command.upgrade(alembic_config, "head")

    with engine.connect() as connection:
        cover = connection.execute(
            text("SELECT cover_version_id FROM assets WHERE id = :id"),
            {"id": "00000000-0000-7000-8000-000000000051"},
        ).scalar_one()
        versions: dict[str, str] = dict(
            connection.execute(text("SELECT file_name || id, status FROM asset_versions")).all()
        )
        jobs: dict[str, str] = dict(
            connection.execute(
                text("SELECT version_id::text, status || ':' || attempts FROM jobs")
            ).all()
        )
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM jobs"))
        connection.execute(text("DELETE FROM asset_versions"))
        connection.execute(text("DELETE FROM assets"))
    engine.dispose()

    assert versions == {
        "a00000000-0000-7000-8000-0000000005a1": "processing",
        "a00000000-0000-7000-8000-0000000005a2": "ready",
        "r00000000-0000-7000-8000-0000000005a4": "processing",
    }
    assert jobs == {
        "00000000-0000-7000-8000-0000000005a1": "queued:0",
        "00000000-0000-7000-8000-0000000005a2": "done:1",
        "00000000-0000-7000-8000-0000000005a4": "running:1",  # a running job is left alone
    }
    assert cover is None  # no cover pointing at a preview that does not exist yet


def test_migration_0005_downgrade_maps_model_reasons_to_one_the_old_check_allows(
    database_url: str, alembic_config: Config
) -> None:
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO assets (id, name, kind, created_at, updated_at)"
                " VALUES ('00000000-0000-7000-8000-000000000053', 'M', 'model', now(), now())"
            )
        )
        connection.execute(
            text(
                "INSERT INTO asset_versions (id, asset_id, number, status, failure_reason,"
                " file_name, content_type, size_bytes, object_key, created_at, updated_at) VALUES"
                " ('00000000-0000-7000-8000-0000000005a3', '00000000-0000-7000-8000-000000000053',"
                " 1, 'failed', 'MODEL_TOO_LARGE', 'm.glb', 'model/gltf-binary', 1,"
                " 'assets/m/v1.glb', now(), now())"
            )
        )

    command.downgrade(alembic_config, "0004_maintenance")
    with engine.connect() as connection:
        reason = connection.execute(text("SELECT failure_reason FROM asset_versions")).scalar_one()
    command.upgrade(alembic_config, "head")
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM asset_versions"))
        connection.execute(text("DELETE FROM assets"))
    engine.dispose()

    assert reason == "PROCESSING_GAVE_UP"


def test_migrations_0006_and_0007_keep_older_assets_without_an_owner_and_clear_keys(
    database_url: str, alembic_config: Config
) -> None:
    engine = create_engine(database_url)
    command.downgrade(alembic_config, "0005_model_previews")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO assets (id, name, kind, created_at, updated_at)"
                " VALUES ('00000000-0000-7000-8000-000000000061', 'Old', 'image', now(), now())"
            )
        )
        connection.execute(
            text(
                "INSERT INTO idempotency_keys (key, operation, request_hash, created_at)"
                " VALUES ('k', 'create_asset', :hash, now())"
            ),
            {"hash": b"\0" * 32},
        )

    command.upgrade(alembic_config, "head")
    with engine.begin() as connection:
        owner = connection.execute(text("SELECT owner_id FROM assets")).scalar_one()
        keys = connection.execute(text("SELECT count(*) FROM idempotency_keys")).scalar_one()
        connection.execute(text("DELETE FROM assets"))
    tables = set(inspect(engine).get_table_names())
    engine.dispose()

    assert owner is None
    assert keys == 0
    assert {"users", "sessions", "access_tokens", "sign_in_failures"} <= tables


def test_migration_0006_downgrades_back_to_anonymous_v0_1(
    database_url: str, alembic_config: Config
) -> None:
    engine = create_engine(database_url)

    command.downgrade(alembic_config, "0005_model_previews")
    tables = set(inspect(engine).get_table_names())
    asset_columns = {c["name"] for c in inspect(engine).get_columns("assets")}
    command.upgrade(alembic_config, "head")
    engine.dispose()

    assert not {"users", "sessions", "access_tokens", "sign_in_failures"} & tables
    assert "owner_id" not in asset_columns


def test_migrations_give_up_on_a_held_lock_instead_of_queueing_writers(
    database_url: str, alembic_config: Config
) -> None:
    """KILN-12 review V4: DDL waits `lock_timeout`, then fails; it never blocks the table."""
    engine = create_engine(database_url)
    command.downgrade(alembic_config, "0005_model_previews")
    hurried = Config(alembic_config.config_file_name)
    hurried.set_main_option("sqlalchemy.url", database_url)
    hurried.cmd_opts = argparse.Namespace(x=["lock_timeout_ms=300"])
    try:
        with engine.connect() as holder:
            holder.execute(text("LOCK TABLE assets IN ROW EXCLUSIVE MODE"))  # a writer at work
            started = time.monotonic()
            with pytest.raises(OperationalError, match="lock timeout"):
                command.upgrade(hurried, "head")
            waited = time.monotonic() - started
            holder.rollback()
    finally:
        command.upgrade(alembic_config, "head")
        engine.dispose()

    assert waited < 5


def test_the_owner_foreign_keys_end_validated(database_url: str) -> None:
    engine = create_engine(database_url)
    with engine.connect() as connection:
        rows: dict[str, bool] = dict(
            connection.execute(
                text(
                    "SELECT conname, convalidated FROM pg_constraint WHERE conname IN"
                    " ('fk_assets_owner_id', 'fk_asset_versions_uploaded_by')"
                )
            ).all()
        )
    engine.dispose()

    assert rows == {"fk_assets_owner_id": True, "fk_asset_versions_uploaded_by": True}


def test_migration_0009_adds_comments_and_downgrades_without_them(
    database_url: str, alembic_config: Config
) -> None:
    engine = create_engine(database_url)

    command.downgrade(alembic_config, "0008_sessions_last_seen_index")
    tables = set(inspect(engine).get_table_names())
    key_columns = {c["name"] for c in inspect(engine).get_columns("idempotency_keys")}
    command.upgrade(alembic_config, "head")
    upgraded = set(inspect(engine).get_table_names())
    upgraded_key_columns = {c["name"] for c in inspect(engine).get_columns("idempotency_keys")}
    engine.dispose()

    assert not {"comment_threads", "comments"} & tables
    assert "resource_id" not in key_columns
    assert {"comment_threads", "comments"} <= upgraded
    assert "resource_id" in upgraded_key_columns


def test_migration_0009_gives_up_while_a_writer_holds_asset_versions(
    database_url: str, alembic_config: Config
) -> None:
    """The new foreign key briefly locks `asset_versions`: behind a writer it fails fast."""
    engine = create_engine(database_url)
    command.downgrade(alembic_config, "0008_sessions_last_seen_index")
    hurried = Config(alembic_config.config_file_name)
    hurried.set_main_option("sqlalchemy.url", database_url)
    hurried.cmd_opts = argparse.Namespace(x=["lock_timeout_ms=300"])
    try:
        with engine.connect() as holder:
            holder.execute(text("LOCK TABLE asset_versions IN ROW EXCLUSIVE MODE"))
            started = time.monotonic()
            with pytest.raises(OperationalError, match="lock timeout"):
                command.upgrade(hurried, "head")
            waited = time.monotonic() - started
            holder.rollback()
    finally:
        command.upgrade(alembic_config, "head")
        engine.dispose()

    assert waited < 5


def test_migration_0010_validates_the_minimum_rectangle_and_downgrades(
    database_url: str, alembic_config: Config
) -> None:
    engine = create_engine(database_url)

    command.downgrade(alembic_config, "0009_comments")
    before = {c["name"] for c in inspect(engine).get_check_constraints("comment_threads")}
    command.upgrade(alembic_config, "head")
    with engine.connect() as connection:
        validated = connection.execute(
            text(
                "SELECT convalidated FROM pg_constraint"
                " WHERE conname = 'ck_comment_threads_rect_min_size'"
            )
        ).scalar_one()
    engine.dispose()

    assert "ck_comment_threads_rect_min_size" not in before
    assert validated is True


_REVIEW_RULES = (
    "ck_asset_versions_review_state",
    "ck_asset_versions_review_revision_non_negative",
    "fk_review_events_version_id",
    "fk_review_events_actor_id",
)


def test_migration_0011_puts_existing_versions_in_review_without_rewriting_the_table(
    database_url: str, alembic_config: Config
) -> None:
    """The backfill plan of KILN-11: a constant default is metadata-only, so the table keeps its
    file (no rewrite), every existing version reads `in_review` at revision 0, and the new rules
    end validated."""
    engine = create_engine(database_url)
    command.downgrade(alembic_config, "0010_comment_rect_min_size")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO assets (id, name, kind, created_at, updated_at)"
                " VALUES ('00000000-0000-7000-8000-000000000111', 'Old', 'image', now(), now())"
            )
        )
        connection.execute(
            text(
                "INSERT INTO asset_versions (id, asset_id, number, status, file_name,"
                " content_type, size_bytes, object_key, created_at, updated_at)"
                " SELECT gen_random_uuid(), '00000000-0000-7000-8000-000000000111', n, 'ready',"
                " 'old.png', 'image/png', 10, 'assets/old/' || n, now(), now()"
                " FROM generate_series(1, 500) AS n"
            )
        )
        file_before = connection.execute(
            text("SELECT pg_relation_filenode('asset_versions')")
        ).scalar_one()

    command.upgrade(alembic_config, "head")
    with engine.begin() as connection:
        file_after = connection.execute(
            text("SELECT pg_relation_filenode('asset_versions')")
        ).scalar_one()
        states = connection.execute(
            text("SELECT review_state, review_revision, count(*) FROM asset_versions GROUP BY 1, 2")
        ).all()
        validated: dict[str, bool] = dict(
            connection.execute(
                text("SELECT conname, convalidated FROM pg_constraint WHERE conname = ANY(:n)"),
                {"n": list(_REVIEW_RULES)},
            ).all()
        )
        triggers = connection.execute(
            text("SELECT tgname FROM pg_trigger WHERE tgrelid = 'review_events'::regclass")
        ).scalars()
        trigger_names = {name for name in triggers if not name.startswith("RI_")}
        connection.execute(text("DELETE FROM assets"))
    engine.dispose()

    assert file_after == file_before
    assert [tuple(row) for row in states] == [("in_review", 0, 500)]
    assert validated == dict.fromkeys(_REVIEW_RULES, True)
    assert trigger_names == {"review_events_append_only"}


def test_migration_0011_downgrades_without_the_review_columns_and_history(
    database_url: str, alembic_config: Config
) -> None:
    engine = create_engine(database_url)
    command.downgrade(alembic_config, "0010_comment_rect_min_size")
    columns = {c["name"] for c in inspect(engine).get_columns("asset_versions")}
    tables = set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        function = connection.execute(
            text("SELECT count(*) FROM pg_proc WHERE proname = 'review_events_append_only'")
        ).scalar_one()
    command.upgrade(alembic_config, "head")
    engine.dispose()

    assert {"review_state", "review_revision"}.isdisjoint(columns)
    assert "review_events" not in tables
    assert function == 0


def test_migration_0011_gives_up_while_a_writer_holds_asset_versions(
    database_url: str, alembic_config: Config
) -> None:
    """Adding the columns needs a brief exclusive lock: behind a writer it fails fast."""
    engine = create_engine(database_url)
    command.downgrade(alembic_config, "0010_comment_rect_min_size")
    hurried = Config(alembic_config.config_file_name)
    hurried.set_main_option("sqlalchemy.url", database_url)
    hurried.cmd_opts = argparse.Namespace(x=["lock_timeout_ms=300"])
    try:
        with engine.connect() as holder:
            holder.execute(text("LOCK TABLE asset_versions IN ROW EXCLUSIVE MODE"))
            started = time.monotonic()
            with pytest.raises(OperationalError, match="lock timeout"):
                command.upgrade(hurried, "head")
            waited = time.monotonic() - started
            holder.rollback()
    finally:
        command.upgrade(alembic_config, "head")
        engine.dispose()

    assert waited < 5
