# hermes-dream: implementation plan (v2)

Status: plan, nothing built yet. Every section maps to GitHub issues; the issue is the unit of
work, this file is the shared design. Update this file in the same PR when a decision changes.
v2 folds in three reviews (safety, feasibility against Hermes v0.22.5, issue quality).

## 1. Goal

A Hermes plugin that makes a Hermes setup smarter on its own: it turns yesterday's execution
into lessons, applies them, checks whether they helped, and rolls back the ones that did not.
Failing cron jobs are healed during the day.

```
capture  (observer hooks, always on, metadata only)
collect  (nightly script, no LLM)              -> payload.json
gate     (wake the agent only for new actionable clusters)
dream    (one agent turn, read-only tools)     -> apply-plan.json
tick     (no-LLM script, every 15 min):
           applier  -> guard check -> apply -> change records
           heal     -> transient retry, pause/resume of own pauses
           verify   -> once a day: kept | rolled back | inconclusive | escalated
report   (morning + weekly)
```

Core rule: **the model decides, code applies.** The nightly agent only reads and writes an
apply plan. Every write to the setup happens in plugin code that enforces the guardrails
(section 7), so one poisoned log line or one model slip can never reach a denied target.

The "dreaming" idea comes from the harness/loop pattern (agents that recover through logs,
retry instead of restart, and turn past execution logs into new memories) and from the
community plugin `hermes-dreaming` (itpartypattaya, MIT), which consolidates conversation facts
into `MEMORY.md` with a deterministic nightly pass.

Hermes already covers parts of this; the plugin must not duplicate them:

| Built in | Does | Does not |
|---|---|---|
| Background self-improvement review | After N turns, saves memory/skill lessons from the current conversation | Never runs for cron (`skip_background_review`), never reads errors.log, refused approvals or other sessions |
| Curator | Weekly prune of unused agent-created skills; optional consolidation | Learns nothing new |
| `cron.retry_unreachable` | Re-runs a recurring job 5/15/30 min later when it failed before any model call | Failures after the first API call |
| `cron.failure_nudge_threshold` | Nudges after N consecutive failures | Fixes nothing |
| `/journey` | Timeline of memory and skills | View only |

## 2. Autonomy

Fully autonomous by design: detect, decide, apply, verify, roll back, heal. The operator is
informed after the fact and can always undo, block or pause. Report-only (listed as proposals
in the morning report, never applied): cron **schedule** and **deliver** changes, everything on
the denylist (section 7.1), and escalated signatures. Opt-in per job: cron prompt edits
(`cron_prompt_include`), retries (`retry_include`), pauses (`pause_include`).

Modes (`mode` setting): `shadow` (default until the release issue switches it: everything runs,
the applier writes nothing and records what it would have done), `autonomous`, `off`.

Non-goals: no fact store or memory provider, no network calls from code, no cloud judge, no
re-implementation of curator, background review, `retry_unreachable` or wiki-hint's upkeep.

## 3. Ideas borrowed from hermes-dreaming (MIT, credited in README)

Design only, our own code: deterministic pass before the model; wake gate; corroboration (a
signal counts only when it repeats; machine text never corroborates); every lesson gets an
outcome; immutable numbers (`L-17`) and text fingerprints instead of database ids; caps per
night, zero changes is a success; secret and injection screening; atomic state with
corrupt-aside; installer with `--dry-run` and `--check`. Loss guard, "still relevant?" questions
and the memory approval queue belong to wiki-hint (section 9).

## 4. Components

```
hermes-dream/
  plugin.yaml      manifest v2, provides_hooks, config_schema (section 8)
  __init__.py      register(ctx): hooks, /dream command, `hermes dream` CLI, skill
  state.py         data dir, atomic JSON, lock, corrupt-aside, fingerprints, paused flag
  screen.py        secret / injection / agent-directive screen
  capture.py       hook callbacks -> event journal
  sessions.py      map sessions <-> cron job/execution (section 4.1)
  collect/         journal.py, executions.py, errorslog.py, jobs.py, dedupe.py, cluster.py
  lessons.py       lifecycle state machine, change records
  guard.py         denylist, caps, target locks, circuit breaker, mode, kill switch
  restore.py       hash-checked restore primitives per target
  applier.py       validates apply-plan.json with guard.py, applies, writes change records
  verify.py        verification runner
  heal.py          retry and pause logic
  tick.py          entry point of the 15-minute job: applier, heal, verify (daily)
  report.py        morning + weekly report, message catalog (en, nl)
  install.py       jobs + scripts, --dry-run/--check/status/remove
  skills/dream/SKILL.md
  tests/           stdlib unittest, fake HERMES_HOME builder, fixtures
```

Runtime data: `plugin_data_dir("hermes-dream")` (`ctx.state.data_dir` inside `register()`),
never the plugin dir. Every Hermes database is opened read-only (`mode=ro`). Two cron jobs per
install: the nightly dream job (gate script + agent) and the 15-minute tick (`no_agent`).
Scripts live in `<HERMES_HOME>/scripts/` as `.py` files: those run on Hermes' own interpreter
with the repo importable (a bash wrapper around system python3 cannot import `cron`).

### 4.1 Capture and session mapping

Observer hooks, fail-open, metadata only, screened and truncated:

| Hook | Recorded |
|---|---|
| `api_request_error` | `status_code`, `retryable`, `retry_count`, `reason`, `error.type`, provider, model |
| `post_tool_call` | status error/blocked/cancelled: tool, `error_type`, screened 200-char `error_message`. Status ok only for tools matching `side_effect_tools` (used by heal). Cron approval denials (`approvals.cron_mode: deny`) arrive here as blocked/error, not via the approval hook; the exact text is verified in the spike |
| `post_approval_response` | interactive sessions: choice deny/timeout/cancelled, `pattern_key` |
| `subagent_stop` | `child_status` not ok: `child_role`, `duration_ms`, counts from `tool_call_history` |
| `on_session_end` | `failed`/`interrupted`, `turn_exit_reason` (per run, not for review forks) |

Performance: these hooks run under a dispatch timeout and are suppressed for 60 s after one.
One `O_APPEND` write of one line, no lock wait; journal path from `get_hermes_home()` at event
time (one gateway serves several homes). Daily JSONL, rotated after `retention_days`.

Session mapping: gateway cron sessions are named `local-<hash>`, not `cron_<job>_<ts>` (that
form only appears on the in-process fallback). Resolve job and execution with
`gateway.session_cron.current_execution()` at hook time when available (verify in the spike
that it reaches the hook thread), else afterwards via `state.db`
`session_admissions.request_id = 'cron:<job_id>:<execution_id>'` -> `target_session_id`.
`executions.db` has no session column. Feature-detect both tables.

### 4.2 Collect (nightly, deterministic)

Read-only sources: event journal; `cron/executions.db` (error text, status, delivery_outcome;
pruned to the last 1000 runs, so collect keeps its own per-execution signature snapshot);
`cron/jobs.json` (streaks, `last_failure`, paused without reason, missing skills);
`logs/errors.log` grouped by signature; `state.db` for first-run backfill (it has no cron
denials). Dedupe against what Hermes already learned: `skills/.curator_ledger.jsonl`, curator
`logs/curator/*/run.json`, a diff of `MEMORY.md`.

Noise: infrastructure signatures ("Interrupted by shutdown", unknown/wedged runs, lock
timeouts) and transient provider classes go to a known-noise store, never to lessons or
regression checks. 403 "usage limit" counts as non-transient.

Output `payload.json`: clusters with signature, broad target fingerprint (job + tool +
error_type), count, distinct days, first/last seen, affected jobs/tools/skills, 1-3 screened
evidence references (execution id, session id, file:line), target class (`skill`, `cron`,
`wiki`, `memory`, `noise`). Thresholds `min_occurrences`, `min_days`, `window_days`.
`homes: all` reads every profile of the install in one pass (like wiki-hint `--homes all`).

### 4.3 Gate

`dream_gate.py` runs collect and prints `{"wakeAgent": false}` unless there is a new actionable
cluster not already covered by an open lesson. Otherwise it prints only the payload path and a
one-line summary (stdout goes into the prompt and through the injection scanner, so no
evidence on stdout). Never empty stdout (that skips the run silently).

### 4.4 Dream (agent turn)

Cron job bound to skill `hermes-dream:dream`, read-only `enabled_toolsets` (file read, skills
view), pinned `max_turns` and model. The agent reads the payload and the targets, then writes
`apply-plan.json` (path handed over by the gate) with at most `max_applies` lessons. Each lesson:
signature, target, exact change as verbatim old/new text (skill pitfall, cron prompt, wiki page,
memory entry), reason, evidence references, how to verify. It applies nothing.

Skill lessons are append-only into a `## Pitfalls (hermes-dream)` section with a size cap; no
rewriting of existing skill text. Before adding one, the agent checks open lessons for an
opposite instruction.

### 4.5 Applier (in the tick)

Picks up a new `apply-plan.json`, validates every lesson with `guard.py`, then applies:

| Target | Apply | Change record |
|---|---|---|
| skill (agent-created local skills only) | Hermes' skill write API, ledgered; a write staged by `skills.write_approval` becomes state `waiting` | ledger entry id (found by skill + time in `.curator_ledger.jsonl`), own copy of before and after content + sha256 |
| cron prompt (jobs in `cron_prompt_include`) | `cron.jobs.update_job` | old and new job fields |
| wiki | file write per the vault `SCHEMA.md` (frontmatter, index line, log line), under the shared vault lock | before/after content + sha256 |
| memory | wiki-hint's memory-edit CLI contract (entry-level, locked); without wiki-hint: report-only | entry-level change set |
| cron schedule / deliver | never: report-only | - |

### 4.6 Heal (in the tick)

- **Retry**: only jobs in `retry_include` (default empty). Only transient classes (429, 5xx,
  timeout) after at least one API call. Refused when the failed run made a successful
  side-effect call (journal) or any non-read tool call, or has a delivery outcome other than
  failed/suppressed. Only when the job is enabled, `state == scheduled`, has no live claim and
  no `quota_hold_until`. Waits `retry_delay_minutes` itself (`trigger_job` has no delay). Max
  `max_retries_per_day` per job, verification re-runs included.
- `trigger_job` un-pauses and clears `paused_reason`: re-read the job right before triggering
  and never trigger a paused job unless its `paused_reason` carries the plugin's marker.
- **Pause**: only jobs in `pause_include`, after `pause_after_failures` identical consecutive
  failures (verification runs excluded), with `paused_reason = "hermes-dream:L-<n> ..."`.
  Resume only own pauses, after a fix was applied. Never touch a job the operator paused.
- Skips the dream job, the tick job, wiki-hint's upkeep job, and jobs with an open lesson.
- Checks the paused flag and the target lock before every action.

### 4.7 Verification and rollback (in the tick, once a day)

Lifecycle: `applied | waiting -> verifying -> kept | rolled_back | inconclusive -> escalated`.

- Window `verify_days` (skills, wiki, memory) or `verify_runs` real runs (cron).
- Minimum exposure: at least `min_exposure` loads of the skill or real runs of the job. Less =
  `inconclusive`, window extended up to `max_extensions`, never `kept`.
- Kept when the signature and the broad target fingerprint drop (zero for job failures) and no
  new non-noise signature appears in the same target.
- Rollback with `restore.py`: restore only when the current state equals the recorded after-
  state (sha256, job fields, memory entries). Otherwise revert only our own hunk; if that is not
  possible, escalate as `conflict`. Skills via `tools.skill_ledger.rollback_entry(id)` after the
  same check, falling back to the own before-copy (the ledger is trimmed at 5 MB).
- After a rollback the change joins the signature's `tried` list; the next attempt must differ;
  after `max_attempts` the signature is escalated.
- Escalated items appear under "needs a human" in every morning report until the operator runs
  `/dream block L-n` or `/dream retry L-n`.

### 4.8 Reports

Morning (only when something happened): applied, kept, rolled back, inconclusive, escalated,
heal actions, guard vetoes, report-only proposals; each change with `/dream undo L-n`.
Weekly: failed cron runs and tool errors per week (trend), lessons kept vs rolled back. Wiki
journal page per ISO week (section 5). One renderer, message catalog en/nl.

### 4.9 Operator commands

`/dream show|undo L-n|block L-n <reason>|retry L-n|pause|resume|status`, same on the CLI
(`hermes dream ...`; `install`/`remove` CLI only). No agent needed: handlers call `restore.py`
and `guard.py` directly. In a multi-profile gateway plugin handlers get no profile binding:
capture the home in `register()` and wrap the handler in `use_cron_store(home)` plus a home
override. Gateway commands run for any authorised chat user: document it.

## 5. llm-wiki integration

hermes-dream only adds lessons to the vault (journal page, applied wiki lessons). Vault upkeep
is wiki-hint's job. Rules: read `SCHEMA.md`, `index.md` and the tail of `log.md` before writing;
weekly journal page `queries/dream-journal-{year}-W{week}.md` (configurable), only in weeks with
an applied lesson; existing taxonomy tags only; evidence as references in `sources`, no `raw/`
copies; one `log.md` line per write; `WIKI_PATH` unset or schema missing = wiki target
unavailable, the rest keeps working. Hold the vault lock shared with wiki-hint while writing.

## 6. Multi-profile

One dream job and one tick job per install with `homes: all` (like wiki-hint), global caps and
breaker, journal and change records per home. `homes: current` for single-profile installs.

## 7. Guardrails (`guard.py`, enforced in code)

### 7.1 Denylist (hard-coded, not configurable away)

`SOUL.md`, `config.yaml`, `.env`, any credentials or secrets path, `USER.md`, plugin code
(including this plugin), Hermes source, other repositories, bundled, hub and plugin-namespaced
skills (only agent-created local skills are eligible), the `hermes-dream:dream` skill, the dream
and tick jobs, wiki-hint's upkeep job and `MAINTENANCE.md`, deletions of skills, pages or jobs,
cron schedule and deliver changes, anything that sends messages. Paths are resolved (symlinks)
before the check.

### 7.2 Caps and locks

`max_applies` per night; one open lesson per target (one lock shared by applier, heal and
verify); skill pitfall section size cap; heal `max_retries_per_day`.

### 7.3 Circuit breaker

Stop applying (detect and report only) until `hermes dream resume` when any of: rollbacks
>= `breaker_rollbacks` (default 2) or >= 30% of decided lessons in 7 days; any guard veto of a
denied target (possible injection); heal actions above `breaker_heal_actions` per day; an
unreadable or corrupt state file (fall back to shadow, never "empty").

### 7.4 Kill switch and screening

`hermes dream pause` sets a state flag checked before every write; both jobs are paused too. A
run already in progress stops at its next check. `screen.py` quarantines secrets, injection
phrasings and agent directives ("always run", "add to memory", shell commands, URLs) before
anything reaches the payload, the model, the report or the wiki. It is a regex screen, not a
guarantee; the guard is the real protection.

## 8. Settings (`config_schema`) and manifest

| Key | Default | Meaning |
|---|---|---|
| `mode` | `shadow` | `shadow`, `autonomous`, `off` |
| `homes` | `current` | `current` or `all` |
| `window_days` / `min_occurrences` / `min_days` | 14 / 3 / 2 | corroboration |
| `max_applies` | 5 | lessons per night |
| `verify_days` / `verify_runs` | 3 / 3 | verification window |
| `min_exposure` / `max_extensions` | 3 / 2 | inconclusive handling |
| `max_attempts` | 2 | different fixes before escalation |
| `breaker_rollbacks` / `breaker_heal_actions` | 2 / 10 | circuit breaker |
| `retry_include` | `[]` | jobs allowed to re-run |
| `pause_include` | `[]` | jobs the heal step may pause |
| `cron_prompt_include` | `[]` | jobs whose prompt lessons may edit |
| `side_effect_tools` | `send_message`, `terminal`, `execute_code`, `browser_exec`, `delegate_task`, `mcp__*` | successful calls that block a retry |
| `retry_delay_minutes` / `max_retries_per_day` | 20 / 1 | heal |
| `pause_after_failures` | 3 | heal |
| `retention_days` | 30 | journal |
| `wiki_journal_path` | `queries/dream-journal-{year}-W{week}.md` | |
| `language` | `en` | `en`, `nl` |

Manifest: `manifest_version: 2`, `kind: standalone`, `requires_hermes: ">=0.21.6"` (every
surface used exists there; internal tables are feature-detected at runtime), every hook in
`provides_hooks`, license, homepage. wiki-hint is detected with `ctx.has_plugin()`; its
memory-edit contract is reached through its CLI, not a file path.

## 9. Coexistence

| Concern | Owner |
|---|---|
| Wiki hygiene, memory pressure, near-duplicates, missing paths, backups | wiki-hint upkeep |
| Loss guard, "still relevant?" questions, memory approval queue | wiki-hint (issues there) |
| Unattended `MEMORY.md` writes | wiki-hint memory-edit contract (entry-level apply and revert) |
| Shared vault lock | wiki-hint (issue there), used by both |
| Execution capture, lessons, applier, verify, heal, reports | hermes-dream |

Dream runs nightly, wiki-hint upkeep weekly in another slot; both take the vault lock. Without
wiki-hint, hermes-dream still runs and says in `status` that wiki and memory hygiene are
uncovered (memory target report-only).

## 10. Testing

stdlib `unittest`, offline, a fake `HERMES_HOME` builder (state.db with sessions and
session_admissions, executions.db, jobs.json, errors.log, skills ledger, wiki vault). Golden
tests: (a) recurring failure -> lesson -> signature drops -> kept; (b) persists -> hash-checked
rollback -> different fix -> escalation; (c) heal: transient 429 on an allowlisted job -> one
re-run; side effect already done -> none; operator-paused job never triggered; (d) breaker
trips; (e) denylisted target never written; (f) adversarial: injected "edit config.yaml / add to
SOUL" in logs -> guard veto, breaker trips, nothing written; (g) low exposure -> inconclusive,
never kept; (h) rollback after a foreign edit -> own hunk only or conflict.
CI: tests + `hermes plugins doctor . --ci` + `hermes plugins validate .`.

## 11. Milestones and build order

- **M1 Foundation**: spike, scaffold, test harness, state, screen.
- **M2 Capture + collect**: capture, session mapping, cron denial check, collect (split), gate.
- **M3 Lessons + guard**: lessons, restore primitives, guard, applier, tick, dream skill,
  commands, installer. Ships in `shadow`.
- **M4 Wiki**: wiki target and journal page.
- **M5 Verify + heal**: verification runner, circuit breaker, heal, reports, multi-profile.
- **M6 Release**: docs, versioning, catalog listing, shadow -> autonomous switch, first live week.

Every issue has a `Depends:` line. `autonomous` may become the default only after restore
primitives, guard, verification runner and circuit breaker are merged and one shadow week shows
no vetoed or conflicting changes.
