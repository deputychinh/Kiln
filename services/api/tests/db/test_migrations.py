import uuid

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, create_engine, inspect, make_url, text

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
