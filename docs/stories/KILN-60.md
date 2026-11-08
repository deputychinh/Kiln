# KILN-60 + KILN-61 + KILN-62: A CRLF password signs in; a stricter search_path check; no test role left behind

- Release: v0.3 · Status: doing · Owner: Claude (deliver-loop) · Debt from the KILN-39/51 final review ([KILN-39](KILN-39.md)); one story for three small items

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
- **API contract, data, UI**: none.

## QA

| AC  | Platform | Test(s)                                                                                                                                                                                                      | Result |
| --- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------ |
| AC1 | cli, api | `test_cli.py::test_the_installed_command_drops_exactly_one_line_ending_and_the_user_signs_in` (LF, CRLF, lone CR, none)                                                                                      | pass   |
| AC2 | cli, api | same test (`\r\r\n`, `\r\r`, `\n\n`)                                                                                                                                                                         | pass   |
| AC3 | cli, api | same test (spaces + CRLF, leading tab + CRLF)                                                                                                                                                                | pass   |
| AC4 | cli, api | `test_the_installed_prompt_without_a_terminal_drops_the_carriage_return_too` (subprocess in a new session, no terminal); `test_the_prompt_drops_one_line_ending_from_each_answer_and_keeps_spaces` (4 cases) | pass   |
| AC5 | db       | not built yet (next commit)                                                                                                                                                                                  | —      |
| AC6 | db       | not built yet                                                                                                                                                                                                | —      |
| AC7 | db       | not built yet                                                                                                                                                                                                | —      |

KILN-60 adds 14 tests (`pytest --collect-only services/api/tests/db/test_cli.py`: 25, was 11). Each subprocess case also tries to sign in with the raw input, its `strip()`ped form and the password plus `\r`, and expects 401 for each that differs from the password.

Exploratory checks: Python's `sys.stdin.readline()` keeps `\r\n` and a lone `\r` (no newline translation on stdin), checked with `printf 'abc\r\n' | python3 -c …`; the subprocess tests feed bytes, so `subprocess.run(text=True)` cannot translate them.

### Mutation testing (by hand, in a git worktree, its own `kiln_k60m_test` database)

| Mutant                                              | Result            |
| --------------------------------------------------- | ----------------- |
| 60-M1 stdin: `rstrip("\n")` only (the original bug) | killed (6 failed) |
| 60-M2 stdin: `rstrip("\r\n")` (every terminator)    | killed (2 failed) |
| 60-M3 stdin: `strip()`                              | killed (4 failed) |
| 60-M4 LF tried before CRLF                          | killed (4 failed) |
| 60-M5 a lone CR not a terminator                    | killed (6 failed) |
| 60-M6 the strip loops past one ending               | killed (3 failed) |
| 60-M7 the first prompt answer not stripped          | killed (4 failed) |
| 60-M8 the repeated prompt answer not stripped       | killed (3 failed) |

## Decisions for the reviewer

- A lone CR counts as a terminator (ADR 0024 §1): it is a real line ending, and an account whose password ends in CR could never sign in from the web anyway.
- The prompt path is fixed too: without a terminal, getpass reads stdin and keeps the CR of a CRLF. With a terminal, ICRNL turns Enter into LF and getpass drops it, so nothing changes there.
- No `Score:` line: the independent review comes after this builder's commits.
