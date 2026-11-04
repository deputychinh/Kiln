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
