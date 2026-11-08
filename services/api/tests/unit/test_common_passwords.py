"""The bundled list of common and breached passwords (KILN-39, ADR 0017)."""

import hashlib
import subprocess
import sys
import time
from importlib import resources

import pytest

from kiln_api.adapters import load_common_passwords
from kiln_api.constants import (
    COMMON_PASSWORDS_FILE,
    COMMON_PASSWORDS_SHA256,
    LONG_BREACHED_PASSWORDS_FILE,
    LONG_BREACHED_PASSWORDS_SHA256,
    PASSWORD_MIN_LENGTH,
)
from kiln_api.domain.identity import password_key, password_length

# Load time in a fresh process; measured about 0.1 s on a laptop, bounded loosely for busy CI.
LOAD_BUDGET_SECONDS = 1.0
LOOKUPS = 100_000
LOOKUP_BUDGET_SECONDS = 0.5


@pytest.mark.parametrize(
    ("name", "checksum"),
    [
        (COMMON_PASSWORDS_FILE, COMMON_PASSWORDS_SHA256),
        (LONG_BREACHED_PASSWORDS_FILE, LONG_BREACHED_PASSWORDS_SHA256),
    ],
)
def test_each_bundled_file_is_the_one_recorded_by_its_checksum(name: str, checksum: str) -> None:
    data = (resources.files("kiln_api") / name).read_bytes()

    assert hashlib.sha256(data).hexdigest() == checksum


def test_at_least_3000_listed_passwords_match_the_length_policy() -> None:
    """ASVS 5.0 V6.2.4: the top 3,000 passwords that match the policy, here 15+ code points."""
    long_enough = [entry for entry in load_common_passwords() if password_length(entry) >= 15]

    assert PASSWORD_MIN_LENGTH == 15
    assert len(long_enough) >= 3_000
    assert {"123456789987654321", "qazwsxedcrfvtgb", "passwordstandard"} <= set(long_enough)


def test_the_list_holds_the_top_passwords_in_their_comparison_form() -> None:
    common = load_common_passwords()

    assert len(common) >= 10_000  # the story asks for at least the top 10,000
    assert {"123456", "password", "qwerty", "passwordpassword", "1qaz2wsx3edc4rfv"} <= common
    assert "Password" not in common  # entries are case-folded, as checks are
    assert all(password_key(entry) == entry for entry in common)
    assert "" not in common


def test_the_list_is_read_once_per_process() -> None:
    assert load_common_passwords() is load_common_passwords()


def test_a_lookup_is_one_hash_probe_whatever_the_list_size() -> None:
    common = load_common_passwords()
    probes = [f"not-on-the-list-{n}" for n in range(LOOKUPS // 2)] + ["passwordpassword"] * (
        LOOKUPS // 2
    )

    started = time.perf_counter()
    hits = sum(probe in common for probe in probes)
    elapsed = time.perf_counter() - started

    assert isinstance(common, frozenset)  # a hash set: O(1) per lookup, not a scan
    assert hits == LOOKUPS // 2
    assert elapsed < LOOKUP_BUDGET_SECONDS


def test_the_list_loads_fast_in_a_fresh_process() -> None:
    """Measured in a new interpreter so no earlier test has warmed the cache."""
    script = (
        "import time\n"
        "from kiln_api.adapters import load_common_passwords\n"
        "started = time.perf_counter()\n"
        "size = len(load_common_passwords())\n"
        "print(size, time.perf_counter() - started)\n"
    )
    result = subprocess.run(  # noqa: S603 - our own interpreter and a fixed script
        [sys.executable, "-c", script], capture_output=True, text=True, check=True, timeout=60
    )
    size, seconds = result.stdout.split()

    assert int(size) >= 10_000
    assert float(seconds) < LOAD_BUDGET_SECONDS
