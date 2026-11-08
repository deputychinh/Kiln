# ADR 0021: One input bound for creating and sending a password; controls do not count, combining marks do

- Status: accepted · 2026-11-08 · Supersedes ADR 0019 §1 (the separate NFKC bound) and corrects its §4 wording; ADRs 0017–0020 stay unedited

## Context

The gate review of KILN-39 (round 2) found three things in ADR 0019's rules. (1) Creation bounded the password's NFKC form at 512, but sign-in's `SignInRequest` bounds the password as typed at 512. A decomposed password such as `"é" * 128` padded with invisible characters (640 typed) was accepted by `make create-user` and then refused with 422 at every sign-in, so the account could never be used. (2) Tab, newline, NUL and the other control characters (Cc), and U+2028/U+2029 (Zl, Zp), counted as visible: `abcdefghijklmn` plus a tab reached 15. They also stayed in the comparison key, so `passwordpassword` plus a tab missed the list. (3) Combining marks count: `"a"` plus 14 × U+0334 is 15 code points. ADR 0019 §4 also said its subset came from "Burnett's ten million"; it comes from the top 1,000,000 of them.

## Decision

1. **One bound, `PASSWORD_INPUT_MAX_LENGTH` = 512, in `constants.py`**, used by `SignInRequest.password` and by `check_new_password` both for the password as typed and for its NFKC form (what is hashed). Every password that can be created can be sent at sign-in; a seeded property test over 3,000 generated passwords (1,399 of them accepted, up to 510 characters) and the edge cases checks it, with exact tests at 512 and 513.
2. **Controls and line or paragraph separators are treated like invisible characters, not refused.** Cc, Zl and Zp join Cf and the default-ignorable code points: they do not count toward the length and are stripped from the comparison key. Not counting them closes the padding. Refusing them would also do that, but it would add a new error the CLI user cannot see on screen (a stray tab typed at the prompt) for no security gain, since the stored hash is unchanged either way. The key's ASCII fast path now applies only to printable ASCII; a test caught it passing a tab through.
3. **Combining marks count, one per code point, as NIST SP 800-63B-4 §3.1.1.2 says** ("Each Unicode code point SHALL be counted as a single character"). They are drawn, and in Devanagari, Thai or Vietnamese they carry the word: counting grapheme clusters instead would make a 15-syllable Hindi passphrase count 5. Stacking marks on one letter is a weak but NIST-compliant password. The list and context checks still apply to it.
4. **Correction to ADR 0019 §4:** the long list holds every entry of 15 or more code points from the **top 1,000,000** of Burnett's ten million (SecLists' `xato-net-10-million-passwords-1000000.txt`), not from all ten million. Folding out control characters turns one list entry into a duplicate, so the lists hold 108,562 distinct keys.

## Consequences

- An operator who pastes a password with a trailing newline or tab gets the same account they would get without it for the length and list checks; the hash still includes the character, as before.
- Known gaps (informational, not built): context words are found only as written, not reversed (`nlik`), not with separators inside them (`k-i-l-n`), and not in leet form (`k1ln`). A future change could normalise these in `_without_context`.

## Sources

NIST SP 800-63B-4 §3.1.1.2 (read 2026-11-08); Unicode UAX #44 (general categories Cc, Zl, Zp; `Default_Ignorable_Code_Point`); UAX #29 (grapheme clusters); ADRs 0017 and 0019.
