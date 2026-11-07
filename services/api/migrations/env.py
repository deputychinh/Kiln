"""Alembic environment: online migrations against KILN_DATABASE_URL.

Every migration session runs with a lock timeout and a statement timeout, so DDL that cannot get
its lock fails fast instead of queueing every writer behind it (KILN-12 review V4). Tests pass
`-x lock_timeout_ms=…` to shorten it.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from kiln_api.config import get_settings
from kiln_api.constants import MIGRATION_LOCK_TIMEOUT_MS, MIGRATION_STATEMENT_TIMEOUT_MS
from kiln_api.db.schema import metadata

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

options = context.get_x_argument(as_dictionary=True)
lock_timeout_ms = int(options.get("lock_timeout_ms", MIGRATION_LOCK_TIMEOUT_MS))
url = config.get_main_option("sqlalchemy.url") or get_settings().database_url
engine = create_engine(
    url,
    connect_args={
        "options": f"-c lock_timeout={lock_timeout_ms}"
        f" -c statement_timeout={MIGRATION_STATEMENT_TIMEOUT_MS}"
    },
)
try:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
finally:
    engine.dispose()  # also when a migration fails, e.g. on its lock timeout
