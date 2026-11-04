from datetime import UTC, datetime, timedelta

from kiln_api.clock import SystemClock


def test_the_system_clock_returns_the_current_utc_time() -> None:
    now = SystemClock().now()

    assert now.tzinfo is UTC
    assert abs(datetime.now(UTC) - now) < timedelta(seconds=1)
