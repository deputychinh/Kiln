# ADR 0017: New passwords need 15 characters and must not be common, breached or guessable from context

- Status: accepted · 2026-11-08 · Supersedes the 12-character minimum of KILN-12 (`docs/security.md`, Accounts)

## Context

KILN-12 let an operator create an account with any password of 12 to 128 characters, so `password1234` was accepted. OWASP ASVS 5.0 V6.2.4 asks that passwords are checked against at least the top 3,000 that match the length policy; NIST SP 800-63B-4 §3.1.1.2 asks for a blocklist of commonly used, expected or compromised values, including context-specific words such as the service's name and the user name, and sets the minimum at **15 characters when a password is the only authentication factor** (8 only when it is part of multi-factor authentication). Kiln has no MFA (KILN-12 left it out of scope). The only place a password is chosen in v0.3 is `make create-user` (`IdentityService.create_user`); there is no sign-up, change or reset yet.

## Decision

1. **Minimum 15, maximum 128**, counted in code points after NFKC as before, never trimmed, no composition rules. 15 and not 12 because a Kiln password is single-factor, which is exactly the case NIST sets at 15; the cost is a longer passphrase for the operator to type once. ASVS L1 alone (8, "15 recommended") would have allowed 12.
2. **An offline blocklist**: the NCSC's top 100,000 passwords from Have I Been Pwned (April 2019), bundled unchanged as SecLists ships it (commit `231fffb`, MIT; upstream under the Open Government Licence v3.0), SHA-256 `c2e56968…c576e0` pinned in `constants.py` and checked by a test. Provenance and both licences sit next to the file (`kiln_api/resources/common-passwords.LICENSE.txt`). It is loaded once per process into a frozenset (about 0.05 s, one hash lookup per check) when the container or the CLI starts, so a missing file fails at startup.
3. **Compared after NFKC, case-folding and NFKC again** (Unicode NFKC_Casefold), on the whole password: `PassWordPassWord` and its full-width form hit `passwordpassword`; `passwordpassword!` does not. The stored hash still keeps the case.
4. **Context words**: "kiln", the email's local part and its pieces of 3 characters or more (`ada.lovelace` → `ada.lovelace`, `lovelace`, `ada`). They are removed (repeatedly, so `kikilnln` goes too) and what is left must still reach the minimum length and not be on the list. A password may contain them (`kiln-glaze-recipes-for-spring` is fine); it is refused only when it is a derivative of them. This keeps NIST's rule that "the entire password SHALL be subject to comparison, not substrings or words that might be contained therein": nothing is refused for containing a word, only for having too little besides it. Shorter pieces are ignored so a two-letter name does not cut into ordinary words.
5. **Problem codes**: `WEAK_PASSWORD` (length), `COMMON_PASSWORD` (on the list), `GUESSABLE_PASSWORD` (context), all 422 subclasses of `WeakPasswordError`. The message says why and what to do and never repeats the password.
6. **No online breach API by default**, and no opt-in Have I Been Pwned k-anonymity check in this change: it would send a hash prefix of every new password to a third party and needs a timeout and a fail-open or fail-closed choice for a command the operator runs a few times a year. If one is added later, it is opt-in, has a timeout and fails open with a logged warning (the offline list still applies); that decision belongs to its own ADR.
7. **Existing passwords keep working.** The rules apply only when a password is chosen; sign-in never checks length or the list, so accounts created under the 12-character rule (or with a password now on the list) sign in as before. Nobody is forced to change a password; a later password-change item can prompt users whose password would now be refused.

## Consequences

- With a 15-character minimum, only 329 of the 97,746 distinct list entries are long enough to matter (`passwordpassword`, `1qaz2wsx3edc4rfv`, `000000000000000`…); the length rule does most of the work, and the list keeps working if the minimum is ever lowered (for example with MFA).
- The repository carries an 835 KB text file; the wheel carries it too.
- A future password change or reset must call `check_new_password` with the user's email and the same list; `IdentityService.create_user` is today's only caller.

## Sources

NIST SP 800-63B-4 (August 2025) §3.1.1.2 Password Verifiers; OWASP ASVS 5.0 V6.2.1, V6.2.4, V6.2.9; NCSC, "Passwords, passwords everywhere" (2019) and its PwnedPasswordsTop100k list; [SecLists](https://github.com/danielmiessler/SecLists) `Passwords/Common-Credentials/100k-most-used-passwords-NCSC.txt`; Unicode UAX #15 and UAX #44 (NFKC_Casefold); ADR 0013.
