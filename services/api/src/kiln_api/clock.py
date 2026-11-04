"""System clock adapter for the `Clock` port."""

from datetime import UTC, datetime


class SystemClock:
    """Wall-clock time in UTC."""

    def now(self) -> datetime:
        """Return the current UTC time."""
        return datetime.now(UTC)
