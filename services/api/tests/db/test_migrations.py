from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

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
