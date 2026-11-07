# Constraints

Last reviewed: 2026-11-07

Plan-only repo: there is no code, test suite or CI yet. The rows below take effect from milestone M1 on; none has been measured.

## Floor (always enforced)
- No secrets, private paths, hostnames or personal names anywhere (public repo).
- Plan §7 guardrails (denylist, caps, verification, rollback, circuit breaker) are never weakened to make a feature work.
- No network calls from code; no dependencies outside the Python standard library.
- From M1 on: no new suppressions (`# noqa`, `# type: ignore`), no bare `except:`, no skipped tests without a reason in the commit message.
- This file is not weakened to make a change pass.

## Enforced with numbers (from M1 on)
| # | Dimension | Rule | Checked by | Runs at |
|---|---|---|---|---|
| 1 | Tests | all green, offline | `python -m pytest` | from M1 on, every change |
| 2 | Lint | zero errors | `ruff check .` | from M1 on, every change |
| 3 | Format | zero diffs | `ruff format --check .` | from M1 on, every change |
| 4 | Plugin | validates | `hermes plugins doctor . --ci` and `hermes plugins validate .` | from M1 on, before every PR |

## Measured ratchets
None yet. From M1 on, record the suppression count (`git grep -nE "# noqa|# type: ignore|except:" -- '*.py' | wc -l`) and skipped-test count with today's real values.

## Exceptions
| ID | Rule | Path | Reason | Expires |
|---|---|---|---|---|
