# AGENTS.md: hermes-dream

Rules for any agent working on this repository.

## Purpose

Learn from execution, safely. Every change must serve one of two goals:

1. Fewer repeated failures (a recurring signature stops after its lesson is applied).
2. Low cost: no model turn on quiet nights, compact payloads, no per-turn prompt injection.

## Before you change anything

- Read `docs/plan.md` fully, then the issue you are working on. The issue is the unit of work;
  one issue per PR. If the plan and the issue disagree, follow the plan and comment on the
  issue.
- Check the real Hermes API before using it: the installed source (`hermes --version`,
  `hermes_cli/plugins.py`, `cron/jobs.py`, `cron/scheduler.py`) and the docs
  (`developer-guide/plugins`, `developer-guide/observer-hooks`, `user-guide/features/cron`).
  Feature-detect optional surfaces (`hasattr(ctx, "register_command")`).

## Hard rules

- Never write to skills, memory files, the wiki, cron jobs or config from scripts or hooks.
  Writes happen only in the apply step after a human "yes", through Hermes' own tools.
- Hooks are observer-only, fail-open, constant time and record metadata only. No prompts, tool
  results, command text or arguments are stored unless screened and truncated.
- Open Hermes databases read-only (`sqlite3` URI `mode=ro`).
- Runtime data goes to `plugin_data_dir("dream")`, never into the plugin directory.
- Atomic state writes; a corrupt state file is moved aside, never treated as empty.
- No network calls from code. No new dependencies outside the Python standard library.
- Public repo: no private paths, hostnames, personal names or tokens in code, tests, fixtures or
  docs. Grep the diff for `/home/`, IP addresses and names before every push.

## Done means

- `python3 -m unittest discover -s tests` green (offline, stdlib only).
- `hermes plugins doctor . --ci` and `hermes plugins validate .` green.
- `plugin.yaml` version bumped on behavior changes, `CHANGELOG.md` updated.
- `docs/plan.md` updated in the same PR when a design decision changed.
- The PR description links the issue and states what was tested and what was not.

## Style

- Python 3.11+, stdlib only, small modules, type hints, no global mutable state outside a lock.
- English in code, docs and user-facing text; report language is a setting.
