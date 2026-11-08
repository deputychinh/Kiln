# ADR 0024: The operator CLI drops exactly one line terminator from a password it reads

- Status: accepted · 2026-11-08 · Supersedes ADR 0021's first Consequence ("the hash still includes the character, as before") for a trailing line terminator read by the CLI; ADRs 0017 and 0021 stay unedited

## Context

`create-user --password-stdin` read one line and removed only a trailing `\n`. A password piped from a file or clipboard with Windows line endings (`\r\n`) kept the `\r`, which was hashed with the rest. HTML password fields strip CR and LF from their value, so the web sign-in can never send that `\r` and the account could never sign in (KILN-60, found in the KILN-39 final review). The interactive prompt has the same hole when it has no terminal: `getpass` then reads stdin and also drops only the `\n`. ADR 0017 says a password is never trimmed, and ADR 0021 says a trailing newline or tab stays in the hash.

## Decision

1. The CLI removes **exactly one** trailing line terminator from what it reads, trying `\r\n`, then `\n`, then a lone `\r` (`CLI_PASSWORD_LINE_ENDINGS` in `constants.py`). `\r\n` is tried first so it goes whole. A lone `\r` counts because it is the classic Mac line ending and, like any CR, no sign-in form can send it.
2. The same rule applies to both answers of the interactive prompt, before they are compared.
3. Nothing else is removed: leading and trailing spaces and tabs, and a second terminator (`pw\r\r\n` creates `pw\r`), stay part of the password. This is reading a line, not trimming a password; ADR 0017's "never trimmed" still holds for the password itself.
4. `--password-stdin` still reads only the first line.

## Consequences

- A password piped with LF, CRLF, a lone CR or no terminator creates the same account, and that account signs in through the API with the password as typed.
- A password that really ends in a CR or LF cannot be set through the CLI; it could not be sent from the web sign-in either.
- Tests run the installed command (`python -m kiln_api.cli`) as a subprocess fed raw bytes, and sign in through the API afterwards.

## Sources

WHATWG HTML Living Standard, `input type=password` value sanitization ("strip newlines from the value"), read 2026-11-08; Python 3.12 `getpass` (the fallback reads `sys.stdin` and removes only `\n`); NIST SP 800-63B-4 §3.1.1.2 (the entire submitted password is verified, not truncated); ADRs 0017 and 0021.
