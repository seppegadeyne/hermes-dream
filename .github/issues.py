#!/usr/bin/env python3
"""One-off: create the planned issues from docs/plan.md. Kept for reference; do not re-run."""
import subprocess

REPO = "seppegadeyne/hermes-dream"
COMMON = ("\n\n---\nRead first: `AGENTS.md`, `docs/plan.md` (sections named above). "
          "Done means: tests green (`python3 -m unittest discover -s tests`), "
          "`hermes plugins doctor . --ci` and `hermes plugins validate .` green, plan updated "
          "if a decision changed, PR links this issue.")

ISSUES = [
 (1, "Scaffold: manifest v2, register(), tests, CI",
  "Plan: §4, §8 Manifest, §8b Testing.\n\n"
  "- `plugin.yaml` manifest v2 (`kind: standalone`, `requires_hermes`, `provides_hooks`, "
  "`config_schema` with every key from §6, license, homepage).\n"
  "- `__init__.py` with `register(ctx)` that registers nothing yet but feature-detects surfaces.\n"
  "- Determine `requires_hermes`: oldest tag that has `inject_message`, `register_skill`, "
  "`register_command`, `register_cli_command`, `ctx.state` and the observer hooks.\n"
  "- `tests/` (stdlib unittest, loads modules by path with a fake ctx) and a GitHub Actions "
  "workflow running the tests plus `hermes plugins validate`.\n"
  "- `CHANGELOG.md`.\n\nAcceptance: doctor and validate green; CI green."),
 (1, "State: atomic JSON, lock, corrupt-aside, fingerprints",
  "Plan: §3 items 5 and 9, §4.\n\n"
  "- `state.py`: data dir from `ctx.state.data_dir` / `plugin_data_dir(\"hermes-dream\")`.\n"
  "- Atomic write (temp + rename, mode 0600), one state lock, corrupt file moved to "
  "`<file>.corrupt-<utc>` and never read as empty.\n"
  "- Text fingerprint helper (normalize numbers, ids, paths, hashes) used for signatures and "
  "proposals.\n\nAcceptance: tests for atomicity, corrupt-aside, lock contention, fingerprint "
  "stability."),
 (1, "Screen: secrets and prompt-injection quarantine",
  "Plan: §3 item 8, §7.\n\n"
  "- `screen.py`: regex screen for common key shapes (sk-, ghp_, gho_, AWS, Google, Slack, "
  "Telegram, JWT, PEM, env assignments) and injection phrasings.\n"
  "- Hit = quarantined: secret text never published, injection keeps a 60-char preview only.\n"
  "- Applied before anything leaves the journal (payload, proposal, report, model context).\n"
  "- Document as \"not a guarantee\".\n\nAcceptance: table-driven tests with positives and "
  "false-positive guards."),
 (2, "Capture: observer hooks to an append-only event journal",
  "Plan: §4.1 (read the field table and the performance rule).\n\n"
  "- Hooks: `api_request_error`, `post_tool_call` (error/blocked/cancelled), "
  "`post_approval_response` (interactive only), `subagent_stop`, `on_session_end`.\n"
  "- Use the real field names listed in §4.1. `job_id` from the `cron_<jobid>_<ts>` session id.\n"
  "- One `O_APPEND` write per event, no lock wait, journal path from `get_hermes_home()` at "
  "event time. Metadata only, screened and truncated.\n"
  "- Daily JSONL files, rotation after `retention_days`.\n\nAcceptance: unit tests per hook "
  "with fake kwargs; a test that a raising callback never propagates; timing test (well under "
  "the dispatch timeout)."),
 (2, "Capture: verify cron approval denials surface in post_tool_call",
  "Plan: §4.1 (approval row), review blocker 1.\n\n"
  "Under `approvals.cron_mode: deny` the denial does not fire `post_approval_response`. Prove "
  "how it reaches `post_tool_call` (status, error_type, exact block message) with a real cron "
  "run in a throwaway `HERMES_HOME`, then encode the detection and add a fixture with the real "
  "text.\n\nAcceptance: documented exact message, detection test, note in plan §4.1."),
 (2, "Collect: deterministic nightly pass and payload",
  "Plan: §4.2.\n\n"
  "- Read-only (`mode=ro`) sources: journal, `cron/executions.db`, `cron/jobs.json` (streaks, "
  "paused without reason, missing skills), `logs/errors.log` grouped by signature, `state.db` "
  "(first-run backfill; note it lacks cron denials).\n"
  "- Dedupe against what Hermes already learned: `skills/.curator_ledger.jsonl`, "
  "`logs/curator/*/run.json`, `MEMORY.md` diff.\n"
  "- Clusters with count, distinct days, first/last seen, affected jobs/tools/skills, 1-3 "
  "screened evidence references, suggested target class.\n"
  "- Thresholds `min_occurrences`/`min_days`/`window_days`; machine-only text never "
  "corroborates. `homes: current|all`.\n\nAcceptance: fixture DBs and logs; golden payload test."),
 (2, "Gate wrapper: wakeAgent output",
  "Plan: §4.3.\n\n"
  "- Bash wrapper in `<HERMES_HOME>/scripts/` calling system `python3` on `collect.py` "
  "(wiki-hint `upkeep.py` wrapper pattern).\n"
  "- Prints `{\"wakeAgent\": false}` on a quiet night, otherwise only payload path + one-line "
  "summary. Never empty stdout, never evidence on stdout.\n\nAcceptance: tests for both outputs; "
  "a quiet fixture night starts no model."),
 (3, "Proposals: numbering, cooldowns, reject list, outcomes",
  "Plan: §3 items 4-6, §4.4, §4.5.\n\n"
  "- Immutable numbers `L-<n>`, keyed by fingerprint.\n"
  "- Outcomes: applied, rejected (reason, `--undo`), waiting (staged by write_approval), or "
  "return after `cooldown_days`; cooldown starts only when shown.\n"
  "- Rejected signal returns only after `reject_reask_days`.\n- Caps: `max_proposals` per night.\n\n"
  "Acceptance: golden test: two nights with the same failure -> one proposal -> cooldown -> "
  "reject -> silence."),
 (3, "Dream skill: hermes-dream:dream procedure",
  "Plan: §4.4, §4.5.\n\n"
  "`skills/dream/SKILL.md` for the nightly turn and the apply turn: read payload, check the "
  "target (skill/wiki/cron prompt) for an existing lesson, write at most `max_proposals` "
  "numbered proposals with evidence, exact change (verbatim old/new), target path, risk and "
  "how to verify; short report. Apply section: per target path (skill_manage patch, memory tool, "
  "llm-wiki procedure, cron edit/pause, trigger_job). No flagged shell commands (cron_mode).\n\n"
  "Acceptance: skill registered as `hermes-dream:dream`; dry run on fixture payload."),
 (3, "/dream command: show, yes, no, apply via inject_message",
  "Plan: §4.5 (review blocker 2).\n\n"
  "- `ctx.register_command(\"dream\", ...)` with args hint, text argument mode.\n"
  "- `show` lists open proposals; `no L-n <reason>` records rejection; `yes L-n` records the "
  "decision and calls `ctx.inject_message(apply prompt, session_key=...)`.\n"
  "- Refuse `yes` while `apply_enabled` is false (shadow mode).\n"
  "- Without gateway injection allowed or without a session: record only and explain "
  "`allow_gateway_injection` / `/dream apply L-n`.\n\nAcceptance: handler tests with fake ctx "
  "for each path; manual test on one messaging platform."),
 (3, "Installer and CLI: hermes dream install/status/pause/remove",
  "Plan: §3 item 10, §4.3, §4.4.\n\n"
  "- `ctx.register_cli_command(\"dream\")`; `install [--paused] [--dry-run]`, `--check`, "
  "`status`, `pause`, `resume`, `remove`.\n"
  "- Copy wiki-hint `upkeep.py` pattern: find job by script name, `create_job(paused=True, "
  "skills=[\"hermes-dream:dream\"], enabled_toolsets=[...], deliver=...)`, update existing.\n"
  "- `--check` warns about `approvals.cron_mode`, missing `allow_gateway_injection`, missing "
  "`WIKI_PATH`, and whether wiki-hint is enabled (`ctx.has_plugin`).\n"
  "- `homes: all` = one job per profile.\n\nAcceptance: idempotent install test; dry-run prints "
  "the plan without writes."),
 (4, "Wiki: dream journal page and apply-to-wiki via llm-wiki procedure",
  "Plan: §5, §9.1.\n\n"
  "- No wiki code module: the apply turn follows the llm-wiki skill and the vault `SCHEMA.md`.\n"
  "- Weekly journal page (`wiki_journal_path`), only when there was a proposal; frontmatter per "
  "schema; `sources` = evidence references; existing tags only.\n"
  "- Applied lesson updates a matching page (bump `updated`) or creates one + `index.md` line; "
  "one `log.md` line per write. No `raw/` copies, no audits or repairs (wiki-hint upkeep).\n"
  "- `WIKI_PATH` unset or schema missing: target reported unavailable.\n\nAcceptance: fixture "
  "vault test of the skill instructions (dry run), and one real write in a test vault."),
 (5, "Transient retry: opt-in re-run via trigger_job",
  "Plan: §4.6.\n\n"
  "- Only jobs in `retry_jobs`; only transient classes (429, 5xx, timeout) after at least one API "
  "call; at most one re-run per job per day after `retry_delay_minutes`; via "
  "`cron.jobs.trigger_job` (note: un-pauses).\n"
  "- Logged and listed in the morning report.\n\nAcceptance: tests incl. never retry when "
  "`api_call_count == 0`, never twice a day, never a job not listed."),
 (5, "Replay links in proposals",
  "Plan: §4.6.\n\nEvery proposal links the failed execution (execution id, session id, cron "
  "output file) so work resumes from evidence instead of starting over.\n\nAcceptance: payload "
  "and proposal contain resolvable references; test with fixture."),
 (5, "Weekly learning report",
  "Plan: §4.7.\n\nProposals made/applied/rejected, top signatures, and before/after counts for "
  "applied lessons (did the signature stop?).\n\nAcceptance: report from fixture history; "
  "delivered through the job's deliver target."),
 (6, "Docs: README install, settings, safety, credits",
  "Plan: §6, §7, §9, README.\n\nInstall steps, every setting, `allow_gateway_injection`, "
  "cron_mode note, shadow mode, what runs where, coexistence with wiki-hint and the built-ins, "
  "credits to hermes-dreaming (MIT).\n\nAcceptance: a fresh reader can install and run "
  "`hermes dream install --check` from the README alone."),
 (6, "Release 0.1.0 and one shadow week",
  "Plan: §10.\n\nRelease with `apply_enabled: false`, install on one Hermes, run one week, "
  "review every proposal by hand (useful / noise / wrong), tune thresholds, record results "
  "in CHANGELOG. Only then enable apply.\n\nAcceptance: shadow-week notes in the issue; "
  "thresholds updated with evidence."),
]

for ms, title, body in ISSUES:
    url = subprocess.run(["gh", "issue", "create", "-R", REPO, "--title", title,
                          "--body", body + COMMON, "--label", "plan",
                          "--milestone", str(ms) and {1: "M1 Foundation", 2: "M2 Capture + collect",
                           3: "M3 Dream + review", 4: "M4 Wiki", 5: "M5 Recover + measure",
                           6: "M6 Release"}[ms]],
                         capture_output=True, text=True)
    print((url.stdout or url.stderr).strip())
