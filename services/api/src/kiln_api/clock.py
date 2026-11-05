"""System clock adapter for the `Clock` port."""

from datetime import UTC, datetime

from sqlalchemy import Engine, func, select


class SystemClock:
    """Wall-clock time in UTC."""

    def now(self) -> datetime:
        """Return the current UTC time."""
        return datetime.now(UTC)


class DatabaseClock:
    """The database's clock, so every worker stamps the same time whatever its own clock says."""

    def __init__(self, engine: Engine) -> None:
        """Ask `engine` for the time."""
        self._engine = engine

    def now(self) -> datetime:
        """Return Postgres `now()` in UTC."""
        with self._engine.connect() as connection:
            moment: datetime = connection.execute(select(func.now())).scalar_one()
        return moment.astimezone(UTC)
