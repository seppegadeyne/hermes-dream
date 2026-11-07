#!/usr/bin/env python3
"""One-off: rewrite the issue plan to plan v2 (three reviews folded in). Keeps issue numbers
where the scope survives, closes merged/obsolete ones, creates the missing ones, and fills in
Depends: lines with real numbers in a second pass."""
import json, re, subprocess

R = "seppegadeyne/hermes-dream"
FOOT = ("\n\n---\nRead first: `AGENTS.md`, `docs/plan.md` (sections named above). Done means: "
        "tests green (`python3 -m unittest discover -s tests`), `hermes plugins doctor . --ci` and "
        "`hermes plugins validate .` green, CHANGELOG entry, plan updated if a decision changed, "
        "PR links this issue.")
MS = {1: "M1 Foundation", 2: "M2 Capture + collect", 3: "M3 Lessons + guard", 4: "M4 Wiki",
      5: "M5 Verify + heal", 6: "M6 Release"}


def gh(*a):
    r = subprocess.run(["gh", *a], capture_output=True, text=True)
    return (r.stdout or r.stderr).strip()


# key -> (existing number or None, milestone, title, depends keys, body)
I = {
 "spike": (None, 1, "Spike: verify the Hermes surfaces the plan relies on", [],
  "Plan: §4.1, §4.6, §4.9, §8.\n\nIn a throwaway `HERMES_HOME`, prove and write down (in "
  "`docs/spike.md`): (1) the exact `post_tool_call` status/error text of a cron approval "
  "denial under `approvals.cron_mode: deny`; (2) whether `gateway.session_cron.current_execution()` "
  "is visible from hook threads, and the `session_admissions` join `cron:<job>:<exec>` -> "
  "session; (3) a `.py` script in `scripts/` can import `cron.jobs` and call `trigger_job`, "
  "`pause_job`, `update_job` during a tick; (4) what `trigger_job` does to paused jobs, "
  "`paused_reason`, `repeat` and interval anchors; (5) `tools.skill_ledger.rollback_entry` "
  "non-interactively; (6) `register_command(..., argument_mode='text')` on one messaging "
  "platform and which home a handler resolves in a multi-profile gateway; (7) a no_agent job's "
  "output and wake behaviour.\n\nAcceptance: `docs/spike.md` with evidence per item; plan "
  "corrected where reality differs."),
 "scaffold": (1, 1, "Scaffold: manifest v2, register(), CI, CHANGELOG", ["spike"],
  "Plan: §4, §8.\n\n`plugin.yaml` (manifest v2, `requires_hermes: \">=0.21.6\"`, "
  "`provides_hooks`, `config_schema` with every key of §8, default `mode: shadow`), "
  "`__init__.py` that feature-detects surfaces, GitHub Actions (tests + `plugins validate`), "
  "`CHANGELOG.md` with a versioning rule (bump on every behaviour change).\n\nAcceptance: "
  "doctor and validate green; CI green."),
 "harness": (None, 1, "Test harness: fake HERMES_HOME builder and fixtures", ["scaffold"],
  "Plan: §10.\n\nOne builder used by every test: state.db (sessions, messages, "
  "session_admissions), executions.db, jobs.json, errors.log, skills dir + "
  "`.curator_ledger.jsonl`, a wiki vault with SCHEMA/index/log, multiple profile homes.\n\n"
  "Acceptance: builder covered by its own tests; schemas match Hermes v0.22.5."),
 "state": (2, 1, "State: atomic JSON, lock, corrupt-aside, fingerprints, paused flag",
  ["harness"],
  "Plan: §4, §7.3, §7.4.\n\n`state.py`: data dir `plugin_data_dir(\"hermes-dream\")`; atomic "
  "write (temp + rename, 0600); one state lock; corrupt file -> `<file>.corrupt-<utc>` and a "
  "breaker trip (never read as empty); the shared fingerprint/normalizer (numbers, ids, paths, "
  "hashes) that every other module reuses; paused flag; change-record schema with before AND "
  "after state (content copies + sha256, job fields, memory entries).\n\nAcceptance: tests for "
  "atomicity, corrupt-aside, lock contention, fingerprint stability."),
 "screen": (3, 1, "Screen: secrets, prompt injection and agent directives", ["harness"],
  "Plan: §7.4.\n\nRegex screen for key shapes (sk-, ghp_, gho_, AWS, Google, Slack, Telegram, "
  "JWT, PEM, env assignments), injection phrasings, and agent directives (\"always run\", "
  "\"add to memory\", shell commands, URLs). Secret hit: no text published; injection/directive "
  "hit: quarantined, no preview to the model. Documented as not a guarantee.\n\nAcceptance: "
  "table-driven tests with positives and false-positive guards."),
 "capture": (4, 2, "Capture: observer hooks to the event journal", ["state", "screen", "spike"],
  "Plan: §4.1.\n\nHooks and fields exactly as in the §4.1 table; `post_tool_call` status ok only "
  "for `side_effect_tools`; one O_APPEND write, path from `get_hermes_home()` at event time; "
  "reuse the fingerprint from the state issue; daily JSONL + rotation.\n\nAcceptance: tests per "
  "hook with fake kwargs; a raising callback never propagates; timing well under the dispatch "
  "timeout."),
 "sessions": (5, 2, "Session mapping and cron approval denials", ["capture", "spike"],
  "Plan: §4.1.\n\n`sessions.py`: job/execution for a session via `current_execution()` or the "
  "`session_admissions` join, feature-detected. Encode cron denial detection with the exact "
  "text from the spike and a fixture.\n\nAcceptance: tests on harness data incl. `local-*` "
  "session ids; denial fixture."),
 "collect-exec": (6, 2, "Collect: journal + executions.db + jobs.json, own signature snapshot",
  ["sessions"],
  "Plan: §4.2.\n\nRead-only collectors; per-execution signature snapshot (executions.db keeps "
  "only 1000 runs); streaks and `last_failure`; noise classes and the known-noise store; 403 "
  "usage limit non-transient.\n\nAcceptance: golden payload from harness data."),
 "collect-logs": (None, 2, "Collect: errors.log grouping and state.db backfill", ["collect-exec"],
  "Plan: §4.2.\n\nGroup WARNING/ERROR lines by normalized signature; first-run backfill of tool "
  "errors from state.db (no cron denials there).\n\nAcceptance: fixture logs -> expected clusters."),
 "collect-dedupe": (None, 2, "Collect: dedupe against curator, skill ledger and MEMORY.md",
  ["collect-exec"],
  "Plan: §4.2.\n\nDrop clusters already covered by `.curator_ledger.jsonl` writes, curator "
  "`run.json`, or a `MEMORY.md` diff; skip the plugin's own sessions and jobs.\n\nAcceptance: "
  "tests per source."),
 "cluster": (None, 2, "Collect: clustering, thresholds, payload and homes: all",
  ["collect-logs", "collect-dedupe"],
  "Plan: §4.2, §6.\n\nCorroboration thresholds, broad target fingerprint, target classes, "
  "screened evidence references, `payload.json` schema, one pass over every home with "
  "`homes: all`.\n\nAcceptance: golden payload incl. two homes."),
 "gate": (7, 2, "Gate script: wakeAgent only for new actionable clusters", ["cluster"],
  "Plan: §4.3.\n\n`dream_gate.py` (Hermes interpreter). `{\"wakeAgent\": false}` unless a new "
  "cluster is not covered by an open lesson; else payload path + one-line summary; never empty, "
  "never evidence on stdout.\n\nAcceptance: tests for both outputs; quiet night starts no model."),
 "lessons": (8, 3, "Lessons: lifecycle state machine and change records", ["state"],
  "Plan: §4.7.\n\n`lessons.py`: numbers `L-<n>`; states applied, waiting (staged by "
  "write_approval), verifying, kept, rolled_back, inconclusive, escalated, conflict; `tried` "
  "list per signature; change records from the state issue. Caps are NOT here (guard issue).\n\n"
  "Acceptance: tests for every transition."),
 "restore": (None, 3, "Restore primitives: hash-checked, per target", ["lessons", "harness", "wh-contract"],
  "Plan: §4.7.\n\n`restore.py`, shared by undo and automatic rollback: restore only when current "
  "state == recorded after-state; else revert only our own hunk; else `conflict`. Skills via "
  "`skill_ledger.rollback_entry` after the check, fallback own before-copy; cron via "
  "`update_job`; wiki file content; memory via the wiki-hint revert contract.\n\nAcceptance: "
  "golden test (h); byte-identical restore when untouched."),
 "guard": (19, 3, "Guard: denylist, caps, target locks, mode, kill switch", ["lessons"],
  "Plan: §7.1, §7.2, §7.4, §2.\n\n`guard.py`: hard-coded denylist with symlink resolution; "
  "eligible skills = agent-created local only; caps; one target lock shared by applier, heal, "
  "verify; `mode`; paused flag checked before every write; opt-in lists. Circuit breaker is a "
  "separate issue.\n\nAcceptance: golden tests (e) and (f, veto part)."),
 "applier": (None, 3, "Applier: validate apply-plan.json and apply per target",
  ["guard", "restore", "gate"],
  "Plan: §4.5.\n\n`apply-plan.json` schema; every lesson through `guard.py`; apply per the §4.5 "
  "table; staged skill write -> `waiting`; schedule/deliver -> report-only; shadow mode records "
  "without writing.\n\nAcceptance: golden tests (a) apply part and (f); shadow writes nothing."),
 "tick": (None, 3, "Tick job: one no_agent .py script for applier, heal and verify",
  ["applier"],
  "Plan: §4, §4.5-4.7.\n\n`tick.py` every 15 min: run applier on a new plan, heal, and verify "
  "once a day; one lock, paused flag, exit fast when idle.\n\nAcceptance: harness test of a full "
  "tick; idle tick under a second."),
 "skill": (9, 3, "Dream skill: hermes-dream:dream writes apply-plan.json", ["applier"],
  "Plan: §4.4.\n\n`skills/dream/SKILL.md`: read payload and targets, append-only pitfalls, "
  "check open lessons for opposite instructions, skip denylisted targets (report-only), write "
  "at most `max_applies` lessons to the plan path. Read-only tools only.\n\nAcceptance: skill "
  "registered as `hermes-dream:dream`; one real run on harness data in shadow."),
 "commands": (10, 3, "/dream and hermes dream: show, undo, block, retry, pause, resume, status",
  ["restore", "guard"],
  "Plan: §4.9.\n\nAction code shared by slash command and CLI; home captured in `register()` and "
  "`use_cron_store(home)`; text argument mode; documented that any authorised chat user can run "
  "it.\n\nAcceptance: handler tests per action; manual test on a multi-profile gateway."),
 "install": (11, 3, "Installer: dream job + tick job, --check, status, remove",
  ["tick", "skill"],
  "Plan: §4, §6.\n\nwiki-hint `upkeep.py` pattern: find jobs by script name, create paused, "
  "update existing; dream job with read-only toolsets, pinned `max_turns`/model; tick job "
  "`no_agent` every 15 min; `--check` reports `cron_mode`, `WIKI_PATH`, wiki-hint presence and "
  "its contract version; `remove` deletes jobs, scripts and (with a flag) data.\n\nAcceptance: "
  "idempotent install; dry-run writes nothing; remove leaves no job."),
 "wiki": (12, 4, "Wiki target: applied lessons and weekly journal page", ["applier", "wh-lock"],
  "Plan: §5.\n\nWiki lessons per the vault `SCHEMA.md` (frontmatter, existing tags, index line, "
  "one log line), journal page only in weeks with an applied lesson, shared vault lock, no "
  "`raw/` copies, unavailable when `WIKI_PATH`/schema missing.\n\nAcceptance: test vault "
  "write + rollback via restore."),
 "verify": (18, 5, "Verification runner", ["tick", "restore"],
  "Plan: §4.7.\n\n`verify.py` daily in the tick: windows, minimum exposure -> inconclusive and "
  "extensions, kept/rolled back, `tried`, escalation after `max_attempts`; noise signatures "
  "excluded from regression checks.\n\nAcceptance: golden tests (a), (b), (g)."),
 "breaker": (None, 5, "Circuit breaker", ["verify", "guard"],
  "Plan: §7.3.\n\nTrips on rollback count/rate, any guard veto, heal actions per day, corrupt "
  "state; stays tripped until `hermes dream resume`.\n\nAcceptance: golden test (d) and the "
  "veto/corrupt cases."),
 "heal": (13, 5, "Heal: opt-in transient retry and pause/resume of own pauses",
  ["tick", "sessions", "guard"],
  "Plan: §4.6.\n\nExactly the §4.6 rules: `retry_include`, `pause_include`, side-effect and "
  "delivery checks, scheduled/no live claim/no quota hold, own delay, `trigger_job` re-read "
  "and marker check, verification runs counted, own jobs and wiki-hint upkeep skipped.\n\n"
  "Acceptance: golden test (c); never retry with 0 API calls, never twice a day, never an "
  "operator-paused job."),
 "report": (20, 5, "Reports: morning and weekly, message catalog en/nl", ["verify", "heal"],
  "Plan: §4.8.\n\nOne renderer, catalog en/nl; morning only when something happened (incl. "
  "inconclusive, vetoes, escalations with `/dream undo|block`); weekly trend of failed runs "
  "and tool errors. Replaces the old weekly-report issue.\n\nAcceptance: both reports from "
  "harness state in both languages."),
 "multi": (None, 5, "Multi-profile: homes: all end to end", ["install", "heal", "verify"],
  "Plan: §6.\n\nOne dream + one tick job per install, per-home journal and records, global "
  "caps and breaker, no double work alongside wiki-hint `--homes all`.\n\nAcceptance: two-home "
  "harness run end to end."),
 "docs": (16, 6, "Docs: README install, settings, safety, credits", ["install", "report"],
  "Plan: all.\n\nInstall, every setting, opt-in lists, shadow vs autonomous, denylist, what "
  "runs where, coexistence with wiki-hint and built-ins, credits to hermes-dreaming (MIT).\n\n"
  "Acceptance: a fresh reader installs and runs `hermes dream install --check` from the README."),
 "catalog": (None, 6, "Catalog listing in the Hermes plugin catalog", ["docs"],
  "Plugin catalog PR (`plugin-catalog/hermes-dream.yaml`, sha-pinned, disclosure of what is "
  "read and written), CI `plugins validate --install-deps`.\n\nAcceptance: catalog PR open."),
 "release": (17, 6, "Release: shadow week, then switch to autonomous", ["breaker", "multi", "docs"],
  "Plan: §2, §11.\n\nRelease 0.1.0 in shadow on one install for a week; review every recorded "
  "lesson (useful / noise / wrong) and tune thresholds; switch the default to `autonomous` "
  "only with no vetoed or conflicting changes in that week; then one autonomous week with "
  "numbers (applied, kept, rolled back, escalated, failed runs before vs after) in the "
  "CHANGELOG.\n\nAcceptance: both weeks documented here."),
}
CLOSE = {14: "Merged into the collect and lessons issues (evidence references are part of the payload and change records).",
         15: "Merged into the reports issue (#20)."}

num = {}
for k, (n, ms, t, deps, b) in I.items():
    if n:
        num[k] = n
for k, (n, ms, t, deps, b) in I.items():
    if k.startswith("wh-"):
        continue
    if not n:
        url = gh("issue", "create", "-R", R, "--title", t, "--body", b + FOOT, "--label", "plan",
                 "--milestone", MS[ms])
        num[k] = int(url.rsplit("/", 1)[-1])
        print("new", num[k], t)
WH = json.loads(open(__file__.replace("issues_v2.py", "wikihint_numbers.json")).read())
num.update(WH)
for k, (n, ms, t, deps, b) in I.items():
    d = ", ".join((f"seppegadeyne/hermes-wiki-hint#{num[x]}" if x.startswith("wh-") else f"#{num[x]}")
                  for x in deps) or "none"
    print(gh("issue", "edit", str(num[k]), "-R", R, "--title", t, "--milestone", MS[ms],
             "--body", f"Depends: {d}\n\n" + b + FOOT))
for n, why in CLOSE.items():
    print(gh("issue", "close", str(n), "-R", R, "--reason", "not planned", "--comment", why))
json.dump(num, open(__file__.replace("issues_v2.py", "issue_numbers.json"), "w"), indent=1)
