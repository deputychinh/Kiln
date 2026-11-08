# KILN-60 + KILN-61 + KILN-62: A CRLF password signs in; a stricter search_path check; no test role left behind

- Release: v0.3 · Status: done (score 9.0/10, one review round) · Owner: Claude (deliver-loop) · Debt from the KILN-39/51 final review ([KILN-39](KILN-39.md)); one story for three small items

## Story

As a **studio's Kiln admin**, I want `create-user` to read a password piped from a Windows file or clipboard (CRLF) the way I typed it, so that the account I create can sign in (KILN-60).

As a **maintainer**, I want the generic search_path test to refuse an unsafe order such as `public, pg_catalog, pg_temp`, so that a future function cannot pass CI with a pin that lets another schema shadow the catalogue (KILN-61).

As a **maintainer running suites in parallel**, I want the DML-only test role dropped after each test, so that the cluster does not collect roles and parallel runs never share one (KILN-62).

INVEST: Independent ☑ (KILN-39 and KILN-51 are done) · Negotiable ☑ (lone CR, the trusted schemas and the leftover check are choices, recorded below and in ADRs 0024 and 0025) · Valuable ☑ (a CRLF account could never sign in) · Estimable ☑ · Small ☑ (one CLI function, one test helper, one fixture) · Testable ☑

## Acceptance criteria

| Id  | Platform | Given                                                                         | When                                                                                                                                                                                                                                  | Then                                                                                                                                                                                                                           |
| --- | -------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| AC1 | cli, api | an operator piping a password into `create-user --password-stdin`             | it ends with LF, CRLF, a lone CR or no terminator                                                                                                                                                                                     | the user is created and signs in through the API (`POST /api/v1/sessions` → 201) with the password without the terminator; the password with a trailing CR is refused (401)                                                    |
| AC2 | cli, api | the same command (edge)                                                       | the input ends with two terminators (`pw\r\r\n`, `pw\r\r`), or two lines (`pw\n\n`)                                                                                                                                                   | exactly one terminator is dropped: `pw\r` is created and signs in, `pw` does not; of two lines only the first is read                                                                                                          |
| AC3 | cli, api | the same command (negative: nothing else trimmed)                             | the password has leading and trailing spaces, or a leading tab, and a CRLF                                                                                                                                                            | the spaces and the tab stay part of the password: it signs in with them and not without them (KILN-39 AC1 "nothing is trimmed")                                                                                                |
| AC4 | cli, api | the interactive prompt, also without a terminal (getpass falls back to stdin) | each answer ends with CR left by a CRLF                                                                                                                                                                                               | both answers lose exactly one terminator before they are compared; spaces stay; the user signs in with the password as typed                                                                                                   |
| AC5 | db       | a function in the `public` schema                                             | its pinned `search_path` names `pg_catalog` after another schema, `pg_temp` anywhere but last, a schema twice, any schema but `pg_catalog`, `public` and `pg_temp` (`"$user"`, `"Public"`, `''`, another), or no `search_path` at all | the generic test reports it with the reason; `pg_catalog, public, pg_temp`, `public, pg_temp` and `pg_catalog, pg_temp` pass; each pin is set on a real function, so the check reads `proconfig` as PostgreSQL stores it       |
| AC6 | db       | the `dml_role` fixture                                                        | a test using it ends, passes or fails                                                                                                                                                                                                 | its role is dropped (`DROP OWNED BY`, then `DROP ROLE`); the role is named `<test database>_dml`, so parallel suites on their own databases never share or drop another's; a role left by a killed run is reused, then dropped |
| AC7 | db       | a whole test run (edge)                                                       | it ends                                                                                                                                                                                                                               | the session fixture fails the run if this database's `_dml` role is still there                                                                                                                                                |

## Non-functional

- Security: OWASP ASVS 5.0 V6.2 (no change to the policy; the account can now sign in); CVE-2018-1058 and the PostgreSQL "Writing SECURITY DEFINER Functions Safely" advice for the search_path rule. No password in test output: failure messages show only `repr` of a fixture password.
- Performance: the KILN-60 tests start ten `python -m kiln_api.cli` processes (about 6 s in all).
- Compatibility: accounts created before are unchanged; only how the CLI reads a line changes.

## Out of scope

- `make create-user` passes no `--password-stdin` flag through (it is interactive only; scripts call `python -m kiln_api.cli` as the e2e setup does). Not changed.
- Leading or trailing spaces in a password: kept (KILN-64 decides the policy for them).
- Leftover `kiln_%_dml` roles of other databases: the check looks only at the run's own database, since another suite may be using its role at that moment.

## References

- WHATWG HTML Living Standard, the `input type=password` value sanitization algorithm: strip newlines from the value (read 2026-11-08).
- Python 3.12 `getpass`: without a terminal it warns and reads `sys.stdin`, removing only `\n`.
- PostgreSQL 17 docs: CREATE FUNCTION, "Writing SECURITY DEFINER Functions Safely" (`pg_temp` last); `search_path` (`pg_catalog` is searched first when not named; `pg_temp` first for relations when not named); DROP OWNED, DROP ROLE ("a role cannot be removed if it is still referenced in any database"; privileges are revoked per database with `DROP OWNED`).
- CVE-2018-1058 (search_path abuse); ADR 0023.

## Design

- **KILN-60, CLI** (`kiln_api/cli.py`): `_without_line_ending(line)` removes the first matching suffix of `CLI_PASSWORD_LINE_ENDINGS = ("\r\n", "\n", "\r")` (`constants.py`) and nothing else. `_read_password` applies it to `stdin.readline()` and to both prompt answers before comparing them. ADR 0024 records the change to ADR 0021's "the hash still includes the character".
- **KILN-61, test** (`tests/db/test_migrations.py`): `_search_path_fault(proconfig)` returns the reason a pin is unsafe or `None`; `_unsafe_functions(connection)` applies it to every function of the `public` schema. `test_every_function_in_the_schema_pins_a_safe_search_path` (renamed from `…_pins_its_search_path_with_pg_temp_last`) asserts none, and `test_the_search_path_check_refuses_an_unsafe_pin_on_a_real_function` creates `public.kiln_probe()` with each of 16 pins in a rolled-back transaction. ADR 0025 records the rule; no migration (today's pin already passes).
- **KILN-62, fixture** (`tests/db/test_review_store.py`): `_dml_role_on(engine)`, a context manager, creates the role if missing (a killed run may have left it), grants DML on `public`, yields, and in `finally` runs `DROP OWNED BY` (revokes its grants in this database) and `DROP ROLE`, with the name quoted by the dialect. `dml_role_name(database)` in `tests/db_fixtures.py` names it; the `database_url` session fixture fails the run if that role is still there. `dml_role` wraps the context manager.
- **API contract, data, UI**: none.

## QA

| AC  | Platform | Test(s)                                                                                                                                                                                                                                                             | Result |
| --- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| AC1 | cli, api | `test_cli.py::test_the_installed_command_drops_exactly_one_line_ending_and_the_user_signs_in` (LF, CRLF, lone CR, none)                                                                                                                                             | pass   |
| AC2 | cli, api | same test (`\r\r\n`, `\r\r`, `\n\n`)                                                                                                                                                                                                                                | pass   |
| AC3 | cli, api | same test (spaces + CRLF, leading tab + CRLF)                                                                                                                                                                                                                       | pass   |
| AC4 | cli, api | `test_the_installed_prompt_without_a_terminal_drops_the_carriage_return_too` (subprocess in a new session, no terminal); `test_the_prompt_drops_one_line_ending_from_each_answer_and_keeps_spaces` (4 cases)                                                        | pass   |
| AC5 | db       | `test_migrations.py::test_the_search_path_check_refuses_an_unsafe_pin_on_a_real_function` (13 unsafe, 3 safe pins); `test_every_function_in_the_schema_pins_a_safe_search_path`                                                                                     | pass   |
| AC6 | db       | `test_review_store.py::test_the_dml_role_is_named_for_its_database_and_dropped_after_use`, `test_the_dml_role_is_dropped_when_the_test_using_it_fails`, `test_a_dml_role_left_by_a_killed_run_is_reused_and_then_dropped`; the two DML attack tests use the fixture | pass   |
| AC7 | db       | `db_fixtures.database_url` teardown (`pytest.fail` when `dml_role_name(<database>)` is in `pg_roles`); killed mutant 62-M1 shows it as an error at teardown; after the full run, `SELECT rolname FROM pg_roles WHERE rolname LIKE 'kiln%\_dml'` returned no rows    | pass   |

KILN-62 adds 3 tests (`pytest --collect-only services/api/tests/db/test_review_store.py`: 43, was 40). KILN-61 adds 16 tests (`pytest --collect-only services/api/tests/db/test_migrations.py`: 41, was 25; the generic test is renamed, not added). KILN-60 adds 14 tests (`pytest --collect-only services/api/tests/db/test_cli.py`: 25, was 11). Each subprocess case also tries to sign in with the raw input, its `strip()`ped form and the password plus `\r`, and expects 401 for each that differs from the password.

Exploratory checks: Python's `sys.stdin.readline()` keeps `\r\n` and a lone `\r` (no newline translation on stdin), checked with `printf 'abc\r\n' | python3 -c …`; the subprocess tests feed bytes, so `subprocess.run(text=True)` cannot translate them.

### Mutation testing (by hand, in a git worktree, its own `kiln_k60m_test` database)

| Mutant                                                                    | Result                                                                                     |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| 60-M1 stdin: `rstrip("\n")` only (the original bug)                       | killed (6 failed)                                                                          |
| 60-M2 stdin: `rstrip("\r\n")` (every terminator)                          | killed (2 failed)                                                                          |
| 60-M3 stdin: `strip()`                                                    | killed (4 failed)                                                                          |
| 60-M4 LF tried before CRLF                                                | killed (4 failed)                                                                          |
| 60-M5 a lone CR not a terminator                                          | killed (6 failed)                                                                          |
| 60-M6 the strip loops past one ending                                     | killed (3 failed)                                                                          |
| 60-M7 the first prompt answer not stripped                                | killed (4 failed)                                                                          |
| 60-M8 the repeated prompt answer not stripped                             | killed (3 failed)                                                                          |
| 61-M1 checker without the `pg_catalog`-first rule                         | killed (1 failed)                                                                          |
| 61-M2 checker without the `pg_temp`-last rule                             | killed (4 failed)                                                                          |
| 61-M3 checker without the each-once rule                                  | killed (2 failed)                                                                          |
| 61-M4 checker without the trusted-schema rule                             | killed (4 failed)                                                                          |
| 61-M5 checker accepts a function with no pin                              | killed (2 failed)                                                                          |
| 61-M6 migration 0016 and `db/schema.py` pin `public, pg_catalog, pg_temp` | killed by the generic test (1 failed); the old check (from `b2c68c4`) passed it (1 passed) |
| 62-M1 no teardown (the fixture as it was)                                 | killed (3 failed, 1 error at session teardown)                                             |
| 62-M2 `DROP ROLE` without `DROP OWNED BY`                                 | killed (3 failed, 3 errors: the grants keep the role)                                      |
| 62-M3 the drop not in `finally`                                           | killed (2 failed)                                                                          |
| 62-M4 one shared role name (`kiln_dml`)                                   | killed (1 failed)                                                                          |

## Decisions for the reviewer

- A lone CR counts as a terminator (ADR 0024 §1): it is a real line ending, and an account whose password ends in CR could never sign in from the web anyway.
- The prompt path is fixed too: without a terminal, getpass reads stdin and keeps the CR of a CRLF. With a terminal, ICRNL turns Enter into LF and getpass drops it, so nothing changes there.
- KILN-61 trusts exactly `pg_catalog`, `public` and `pg_temp`, and allows `pg_catalog` to be left out (PostgreSQL then searches it first). A bare `pg_temp` passes the order rule; table names must still be qualified (ADR 0023).

## Known gaps (filed)

- KILN-65: a bare `pg_temp` or `pg_catalog, pg_temp` pin passes the check although unqualified relations then resolve to `pg_temp`; `''` needs a clearer reason.
- KILN-66: a role left by a SIGKILLed run fails a later run that never uses `dml_role` (drop it at session start); no test proves the leftover check fires (mutant 62-a survived).
- KILN-67: EOF at the prompt gives a raw `EOFError` traceback; `make create-user` cannot pass `--password-stdin`.

## Review rounds

| Round | Reviewer           | Score | Outcome                                                       |
| ----- | ------------------ | ----- | ------------------------------------------------------------- |
| 1     | independent, fresh | 9.0   | shipped; reliability and security gaps filed as KILN-65 to 67 |

## Score

| #   | Criterion           | Score                                                                                         |
| --- | ------------------- | --------------------------------------------------------------------------------------------- |
| 1   | Requirements fit    | 1                                                                                             |
| 2   | Test depth          | 1                                                                                             |
| 3   | Reliability         | 0.5 (a role left by a killed run fails a later unrelated run; EOF at the prompt: KILN-66, 67) |
| 4   | Security            | 0.5 (a bare `pg_temp` or `pg_catalog, pg_temp` pin passes the check: KILN-65)                 |
| 5   | Maintainability     | 1                                                                                             |
| 6   | UX / API ergonomics | 1                                                                                             |
| 7   | Accessibility       | 1 (no UI change)                                                                              |
| 8   | Performance         | 1                                                                                             |
| 9   | Docs                | 1                                                                                             |
| 10  | Delivery            | 1                                                                                             |
|     | **Total**           | **9.0**                                                                                       |

Retro: a cluster-wide test object (a role) must be cleaned at session start as well as at teardown, or one killed run breaks every later run on that database; a leftover check needs its own mutant (point it at the wrong name).
