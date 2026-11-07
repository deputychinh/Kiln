from kiln_api.adapters import Argon2PasswordHasher
from kiln_api.container import build_hasher

PASSWORD = "correct horse battery staple"  # noqa: S105 - test value


def test_passwords_are_hashed_with_argon2id_at_the_owasp_parameters() -> None:
    """OWASP Password Storage Cheat Sheet: m=19456 KiB, t=2, p=1."""
    encoded = build_hasher().hash(PASSWORD)

    assert encoded.startswith("$argon2id$v=19$m=19456,t=2,p=1$")


def test_the_same_password_hashes_differently_each_time() -> None:
    hasher = Argon2PasswordHasher(memory_kib=64, time_cost=1, parallelism=1)

    assert hasher.hash(PASSWORD) != hasher.hash(PASSWORD)


def test_verification_accepts_the_password_and_refuses_anything_else() -> None:
    hasher = Argon2PasswordHasher(memory_kib=64, time_cost=1, parallelism=1)
    encoded = hasher.hash(PASSWORD)

    assert hasher.verify(encoded, PASSWORD)
    assert not hasher.verify(encoded, PASSWORD + " ")
    assert not hasher.verify("not a hash", PASSWORD)


def test_a_hash_made_with_other_parameters_needs_a_rehash() -> None:
    cheap = Argon2PasswordHasher(memory_kib=64, time_cost=1, parallelism=1)

    assert build_hasher().needs_rehash(cheap.hash(PASSWORD))
    assert not cheap.needs_rehash(cheap.hash(PASSWORD))
