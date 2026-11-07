# hermes-dream: implementation plan (v4)

Status: plan, nothing built yet. Every section maps to GitHub issues; the issue is the unit of
work, this file is the shared design. Update this file in the same PR when a decision changes.
v4 folds in review round 4 (plan binding by hash, job-definition drift, allowlist slots,
read tools for targets); v3 folded in two review rounds (security/adversarial, feasibility against Hermes v0.22.5,
consistency); v2 folded in the first three.

## 1. Goal

A Hermes plugin that makes a Hermes setup smarter on its own: it turns yesterday's execution
into lessons, applies them, checks whether they helped, and rolls back the ones that did not.
Failing cron jobs are healed during the day.

```
capture  (observer hooks, always on, metadata only)
collect  (nightly script, no LLM)              -> payload.json
gate     (wake the agent only for new actionable clusters)
dream    (one agent turn, plugin read-only toolset) -> apply plan (final response)
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
  applier.py       authenticates the dream output, validates the apply plan with guard.py, applies, writes change records
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
| `post_tool_call` | status error/blocked/cancelled: tool, `error_type`, screened 200-char `error_message`. Status ok only for tools matching `side_effect_tools` (used by heal). |
| `on_skill_lifecycle` | `action="loaded"` (covers `skill_view`, cron `skills:` injection and slash commands): skill name, job id when in cron. This is the exposure signal for verification; the dream skill itself is excluded |
| `post_llm_call` | dream-job executions only (`ctx.current_cron_execution().job_id == dream_id`): `{execution_id, sha256(assistant_response)}` to plugin state; this binds the plan (4.4) |
| (note) | Cron approval denials (`approvals.cron_mode: deny`) arrive in `post_tool_call` as blocked/error, not via the approval hook; the exact text is verified in the spike |
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

Cron job bound to skill `hermes-dream:dream`, `deliver: local` (the plan never goes to chat),
model pinned at install (`model`, `provider`, `pinned: true`; shown by `--check`).

**The toolset is the real control.** Hermes' `file` toolset contains `write_file`/`patch` and
`skills` contains `skill_manage`, and a per-job toolset list silently gets every enabled MCP
server added unless it contains `no_mcp`. So the plugin registers its own toolset
`hermes-dream-ro` with three read-only tools (`dream_read_payload`, `dream_read_skill`,
`dream_read_lessons`) that can read only the plugin data dir and eligible skills, and the job
runs with `enabled_toolsets: [hermes-dream-ro, no_mcp]`. No `delegate_task`, no `execute_code`,
no generic `read_file` (no exfiltration of arbitrary files).

Read tools (all take names, never paths; each handler re-checks that the caller is the dream
execution, and `check_fn` hides them from every other session):
- `dream_read_payload()`: the payload, which already carries the verbatim current text of every
  candidate target (job prompt for jobs in `cron_prompt_include`, wiki page under
  `dream_wiki_dir`, memory entries), screened and size-capped;
- `dream_read_skill(name)`: looked up in the skills index; rejects `/`, `..`, NUL; realpath must be
  under `<home>/skills`, not `.hub`, not an external dir, no symlink on the path; `SKILL.md` only,
  size-capped, screened;
- `dream_read_lessons()`: open lessons and `tried` lists.

With Tool Search on (live config: `auto`), plugin tools are deferred behind
`tool_search`/`tool_describe`/`tool_call`; the skill says to call them through `tool_call`. The
hook sees the real name after unwrapping; catalog reads are bounded only by `agent.max_turns`.
If the plugin is not enabled in the profile the job runs with zero tools; `--check` verifies the
toolset is registered.

**Second layer: a `pre_tool_call` hook.** Hermes fails `pre_tool_call` closed (a raising or
slow hook blocks every tool call in every session), so the hook does no I/O: one
`ctx.current_cron_execution()` read (public API, reaches tool and hook threads, `None` outside
cron and for children), compared with the cached dream job id; anything else returns `None`
immediately. Whole body in `try/except: return None`; a block always carries a message. Test:
under 1 ms. In dream sessions it blocks every tool outside `hermes-dream-ro` and counts tool
calls per execution, blocking after `dream_max_tool_calls` (default 40). There is no per-job
`max_turns` in Hermes (the global `agent.max_turns` applies; `--check` shows it), so this
counter is the turn budget.

The agent does not write files. Its **final response** is the apply plan: one fenced ```json
block (schema in section 11) with at most `max_applies` lessons. Hermes saves it to
`cron/output/<dream-job>/<ts>.md` (header, `## Prompt`, `## Response`; mode 0600, 50 kept).

**Plan authorship.** A nonce is not a secret (it sits in the saved prompt and plugin state,
both readable by any same-user session), so the binding is a hash: the plugin's `post_llm_call`
hook records `sha256(final_response)` for the dream execution (4.1). The tick accepts a plan only
when (1) a successful `executions.db` row of the dream job exists whose `source` is the
scheduler or the `hermes dream` CLI, (2) exactly one output file falls inside that row's
`started_at..finished_at` (filenames are local time) and its framed `## Response` (Hermes'
`_archive_answer` framing, length-checked) hashes to the recorded value, and (3) both job
definitions are unchanged (7.6). Anything else is `forged_plan`. Exactly one fenced block; zero, several or malformed = run recorded as
`no_plan`, nothing applied. Processed files are tracked by execution id. Each lesson:
signature, target, exact change as verbatim old/new text (skill pitfall, cron prompt, wiki page,
memory entry), reason, evidence references, how to verify. It applies nothing.

Skill lessons are never free text. The agent fills a fixed template (`symptom`, `cause`,
`fix`; each max 200 chars). Slots are NFKC-normalized and checked against an allowlist: one
line; letters, digits, space and `.,;:'()-` only; Unicode categories Cf, Mn, Co rejected; each
slot must name the cluster's tool, job or error type. A blocklist (below) is only a second
pass. Code renders it escaped inside a blockquote into a `## Pitfalls (hermes-dream)` section,
each item wrapped in `<!-- hermes-dream:L-n sha256 -->` markers, under a header saying the
section is auto-generated and must not be followed where it weakens safety. Slot validation
rejects backticks, `!`, `${`, URLs, paths outside the skill, and security vocabulary
(approval, config, token, secret, env, sudo, curl, wget, ssh, chmod, `| bash`). The agent checks
open lessons for an opposite instruction before proposing one.

### 4.5 Applier (in the tick)

Picks up the newest unprocessed, authenticated dream output (4.4), screens every lesson text with `screen.py` (all
targets, memory and skill included), validates it with `guard.py`, then applies. `guard.py`
also enforces "the next attempt must differ" (fingerprint of the change vs the signature's
`tried` list). Targets whose issue is not merged yet (e.g. wiki before M4, memory before the
wiki-hint contract) are recorded as report-only:

| Target | Apply | Change record |
|---|---|---|
| skill (agent-created local skills only; report-only when `approvals.cron_mode` is `approve` and the skill is bound to or loadable by a job whose resolved toolsets (`_resolve_cron_enabled_toolsets`; `None` = platform default incl. terminal) include terminal, code or MCP) | Hermes' skill write API, ledgered; a write staged by `skills.write_approval` becomes state `waiting` | ledger entry id (found by skill + time in `.curator_ledger.jsonl`), own copy of before and after content + sha256 |
| cron prompt (jobs in `cron_prompt_include`) | `cron.jobs.update_job` under the cron store lock (`_jobs_lock`, feature-detected; it falls back to in-process after 30 s, so check before acting); report-only when the job's resolved toolsets (inherited = all) include terminal, code or MCP, or `approvals.cron_mode` is `approve` (an injected prompt would run unattended) | old and new job fields |
| wiki | only when wiki-hint with the untrusted-pages feature is enabled (else report-only); file write per the vault `SCHEMA.md`; guard requires the resolved path under `dream_wiki_dir` (default `queries/dream/`); frontmatter `source: hermes-dream`, `trust: untrusted`; text through the slot allowlist; wiki-hint excludes such pages from hint injection and from its upkeep agent's instructions (wiki-hint issue); under the shared vault lock | before/after content + sha256 |
| memory | wiki-hint's memory-edit CLI contract (entry-level, locked); without wiki-hint: report-only | entry-level change set |
| cron schedule / deliver | never: report-only | - |

### 4.6 Heal (in the tick)

- **Retry**: only jobs in `retry_include` (default empty). Only transient classes (429, 5xx,
  timeout) after at least one API call. Refused when the failed run made any successful call
  to a tool matching `side_effect_tools` (journal; that setting is the definition, default
  covers every sending, shell and MCP tool), or has a delivery outcome other than
  failed/suppressed. Only when the job is enabled, `state == scheduled`, has no live claim and
  no `quota_hold_until`. Waits `retry_delay_minutes` itself (`trigger_job` has no delay). Max
  `max_retries_per_day` per job, verification re-runs included.
- `trigger_job` un-pauses and clears `paused_reason`: re-read the job right before triggering
  and never trigger a paused job unless its `paused_reason` carries the plugin's marker.
- **Pause**: only jobs in `pause_include`, after `pause_after_failures` identical consecutive
  failures (verification runs excluded). The pause creates a heal record `H-<n>` and sets
  `paused_reason = "hermes-dream:H-<n> ..."`; collect reads open `H-n` records and turns each into a cluster for the next dream run. When a
  lesson for that job is applied (state `verifying`), the tick resumes the job itself (own
  marker only) and triggers one verification run (`trigger_job`, counted against
  `max_retries_per_day`). Never touch a job the operator paused. A pause counts as our own
  only when it matches a stored `H-n` record (job id, `paused_at`, reason hash); the marker
  the marker string alone proves nothing. `closed_at` is set when the job is resumed by us,
  resumed or edited by someone else, or deleted.
- Every trigger/pause is a compare-and-swap: under the cron store lock, re-read the job and
  re-check state, live claim and pause record, then act (`trigger_job` itself un-pauses,
  clears `paused_reason` and ignores live claims). Use `trigger_job` only, never `resume_job`
  (that can add an uncounted catch-up run). Verification runs are the ones the tick triggers;
  `trigger_job` stamps `manual_run_at`, which tells them apart. Triggered verification runs
  count toward `verify_runs`; resuming our own pause is done with `trigger_job` (it un-pauses).
- The tick always exits 0 (a non-zero exit sends a "script failed" alert every 15 minutes).
- **Retries** skip jobs with an open lesson (the verification runs are verify's job).
- Skips the dream job, the tick job and wiki-hint's upkeep job.
- In `shadow` mode heal records what it would do and acts on nothing.
- Checks the paused flag and the target lock before every action.

### 4.7 Verification and rollback (in the tick, once a day)

Lifecycle: `applied -> verifying -> kept | rolled_back | inconclusive | conflict -> escalated`.
`waiting` (staged by `skills.write_approval`, `pending_id` stored) becomes `verifying` when the
pending write is approved, and closes as `rolled_back` when it is rejected or disappears.
`applied` becomes `verifying` at the next tick after the write is confirmed on disk.
Exposure for skills is counted from `on_skill_lifecycle` "loaded" events in the journal; for
jobs from real runs (scheduled or triggered).

- Window `verify_days` (skills, wiki, memory) or `verify_runs` real runs (cron).
- Minimum exposure: at least `min_exposure` loads of the skill or real runs of the job. Less =
  `inconclusive`, window extended up to `max_extensions`, never `kept`.
- Kept when the signature and the broad target fingerprint drop (zero for job failures) and no
  new non-noise signature appears in the same target.
- Rollback with `restore.py`: restore only when the current state equals the recorded after-
  state (sha256, job fields, memory entries). Otherwise revert only our own hunk: skills by the
  `hermes-dream:L-n` marker block; wiki and cron prompts by replacing the exact `new` text with
  `old` when `new` still occurs exactly once; memory through the wiki-hint revert. Anything
  else is `conflict` and escalates. Skills via `tools.skill_ledger.rollback_entry(id)` after the
  same check, falling back to the own before-copy (the ledger is trimmed at 5 MB). Skill
  pitfalls are found by their `hermes-dream:L-n` marker across all skills (survives curator
  merges and renames); the file is re-hashed right before the atomic rename and again after,
  a mismatch is `conflict`.
- After a rollback the change joins the signature's `tried` list; the next attempt must differ;
  after `max_attempts` the signature is escalated.
- Escalated items appear under "needs a human" in every morning report until the operator runs
  `/dream block L-n` or `/dream retry L-n`.

### 4.8 Reports

Sending: the tick is a `no_agent` job, and Hermes delivers its stdout to the job's deliver
target. The tick prints the morning report once a day (and the weekly report on Mondays) when
there is something to say, else nothing (silent run). The plugin itself never sends messages.

Reports show code-built fields and lesson ids; slot text is truncated and re-screened, never
raw agent output.

Morning (only when something happened): applied, kept, rolled back, inconclusive, escalated,
heal actions, guard vetoes, report-only proposals; each change with `/dream undo L-n`.
Weekly: failed cron runs and tool errors per week (trend), lessons kept vs rolled back. Wiki
journal page per ISO week (section 5). One renderer, message catalog en/nl.

### 4.9 Operator commands

`/dream show|undo L-n|block L-n <reason>|retry L-n|pause|status`, same on the CLI
(`hermes dream ...`). `resume` (clears both the kill switch and a tripped breaker), `install`
and `remove` are CLI-only, so a chat user cannot re-arm the system after an injection tripped
the breaker. No agent needed: handlers call `restore.py`
and `guard.py` directly. In a multi-profile gateway plugin handlers get no profile binding:
capture the home in `register()` and wrap the handler in `use_cron_store(home)` plus a home
override. Gateway commands run for any authorised chat user: document it.

## 5. llm-wiki integration

hermes-dream only adds lessons to the vault (journal page, applied wiki lessons). Vault upkeep
is wiki-hint's job. Rules: read `SCHEMA.md`, `index.md` and the tail of `log.md` before writing;
weekly journal page `queries/dream/journal-{year}-W{week}.md` (inside `dream_wiki_dir`, same untrusted frontmatter), only in weeks with
an applied lesson; existing taxonomy tags only; evidence as references in `sources`, no `raw/`
copies; one `log.md` line per write; `WIKI_PATH` unset or schema missing = wiki target
unavailable, the rest keeps working. Hold the vault lock shared with wiki-hint while writing.

## 6. Multi-profile

One dream job and one tick job per install; with `homes: all` (like wiki-hint) they cover every profile, global caps and
breaker, journal and change records per home. `homes: current` for single-profile installs.

## 7. Guardrails (`guard.py`, enforced in code)

### 7.1 Denylist (hard-coded, not configurable away)

`SOUL.md`, `config.yaml`, `.env`, any credentials or secrets path, `USER.md`, plugin code
(including this plugin), Hermes source, other repositories, bundled, hub and plugin-namespaced
skills (only agent-created local skills are eligible), the `hermes-dream:dream` skill, the dream
and tick jobs, wiki-hint's upkeep job and `MAINTENANCE.md`, deletions of skills, pages or jobs,
cron schedule and deliver changes, lessons that make a job or skill send messages. Paths are resolved (symlinks)
before the check.

### 7.2 Caps and locks

`max_applies` per night; one open lesson per target (one lock shared by applier, heal and
verify); skill pitfall section size cap (`pitfall_max_chars`, default 2000 per skill; full = report-only);
heal `max_retries_per_day`. Vault lock wait: 30 s, then skip and retry next tick.

### 7.3 Circuit breaker

Veto classes: `tool_block` (the dream agent tried a tool outside its toolset: logged, counted,
trips only at `breaker_tool_blocks` per run, default 5); `denied_target` (a lesson in an
authenticated plan targets the denylist: possible injection); `forged_plan` (an output file
failed authentication); `screen_hit` (lesson text failed the screen or slot validation).

Stop applying (detect and report only) until `hermes dream resume` (CLI) when any of: rollbacks
>= `breaker_rollbacks` (default 2) or >= 30% of decided lessons in 7 days; any `denied_target`
or `forged_plan`; `screen_hit` >= 2 in 7 days; `tool_block` over its threshold; heal actions
above `breaker_heal_actions` per day; an unreadable or corrupt state file (fall back to shadow,
never "empty").

### 7.4 Environment checks

`hermes dream install --check` and every tick refuse `autonomous` (fall back to shadow, say why)
when `skills.inline_shell` is true (a pitfall with `` !`cmd` `` would run on every skill load).
`--check` also warns when `approvals.cron_mode` is `approve` and shows the effective
`agent.max_turns`.

### 7.5 Kill switch and screening

`hermes dream pause` sets a state flag checked before every write; both jobs are paused too. A
run already in progress stops at its next check. `screen.py` quarantines secrets, injection
phrasings and agent directives ("always run", "add to memory", shell commands, URLs) before
anything reaches the payload, the model, the report or the wiki. It is a regex screen, not a
guarantee; the guard is the real protection.

### 7.6 Job-definition drift

Any same-user session can change the dream or tick job through the `cronjob` tool (prompt,
skills, toolsets, script, deliver, `context_from`, `no_agent`) without an ownership check. At
install the plugin stores a hash of both job definitions (prompt, skills, enabled_toolsets,
script, model, provider, deliver, context_from, workdir, no_agent). Every tick compares; drift
= `forged_plan` + breaker trip + morning report. `status` also lists any other job with
`context_from` pointing at the dream job.

### 7.7 Tamper-evident breaker

Breaker events and the paused flag are an append-only, hash-chained log in plugin data (that
dir is not write-protected by Hermes). `resume` appends an entry; a chain that does not verify
counts as a trip. A same-user terminal can still defeat this; documented as a limit.

## 8. Settings (`config_schema`) and manifest

| Key | Default | Meaning |
|---|---|---|
| `mode` | `shadow` | `shadow`, `autonomous`, `off` (`off`: hooks record nothing, gate never wakes, tick does nothing) |
| `homes` | `current` | `current` or `all` (one dream + one tick job per install either way; wiki-hint calls `current` "self") |
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
| `wiki_journal_path` | `queries/dream/journal-{year}-W{week}.md` | inside `dream_wiki_dir`, same untrusted frontmatter |
| `pitfall_max_chars` | 2000 | per-skill size cap of the hermes-dream pitfall section |
| `dream_max_tool_calls` | 40 | tool calls per dream run (the hook enforces it) |
| `breaker_tool_blocks` | 5 | blocked tool attempts per dream run before the breaker trips |
| `dream_schedule` | `0 3 * * *` | nightly dream job |
| `report_hour` | 7 | local hour of the morning report and the daily verify pass |
| `tick_deliver` | install origin | deliver target of the tick (reports) |
| `dream_wiki_dir` | `queries/dream/` | vault folder for dream pages |
| `language` | `en` | `en`, `nl` |

Manifest: `manifest_version: 2`, `kind: standalone`, `requires_hermes: ">=0.21.6"` (every
surface used exists there; internal tables are feature-detected at runtime), every hook in
`provides_hooks`, license, homepage. In `register()` wiki-hint is detected with `ctx.has_plugin()`;
scripts (gate, tick) have no `ctx` and detect its contract with
`hermes wiki-hint memory-edit --contract`. Scripts read `plugins.entries.hermes-dream.settings`
themselves, and `ctx.get_config` does not apply schema defaults: pass defaults in code. List
settings have no item types (raw JSON in the UI): validate in code.

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

## 11. Schemas (versioned, each with a test fixture)

All JSON carries `"schema": <name>` and `"version": 1`. The issue that first writes a schema
defines it in `docs/schemas.md` with an example; later issues extend, never rename.

- **payload** (`plugin-data/.../payload.json`, written by collect): `run_id`,
  `generated_at`, `homes`, `clusters[]` = {`cluster_id` (signature fingerprint), `signature`,
  `target_fp`, `class`, `count`, `days`, `first_seen`, `last_seen`, `jobs[]`, `tools[]`,
  `skills[]`, `evidence[]` = {`kind`, `ref`}}, `open_lessons[]`, `tried{}`.
- **apply plan** (agent final response, bound by response hash): `lessons[]` = {`cluster_id`, `target` =
  {`kind`: skill|cron_prompt|wiki|memory, `name`: skill name / job id / vault path / memory
  entry text}, `change` (skill: `symptom`/`cause`/`fix`; cron_prompt and wiki: `old`/`new`
  verbatim, `old` empty = append; memory: `add`/`replace`), `reason`, `verify`},
  `report_only[]` (same shape, plus `why`). Code assigns `L-n`, never the agent.
- **change record** (`lessons/L-n.json`): `lesson`, `state`, `target`, `before`, `after`
  (content or fields, sha256), `ledger_id`, `pending_id`, `applied_at`, `verify` = {`window`,
  `exposure`, `baseline`, `observed`}, `history[]`.
- **heal record** (`heal/H-n.json`): `job_id`, `kind` (retry|pause), `execution_id`,
  `paused_at`, `reason_hash`, `lesson` (when linked), `closed_at`, `outcome`.

Memory changes use wiki-hint's "memory change set" (wiki-hint issue), referenced by id.

## 12. Milestones and build order

- **M1 Foundation**: spike, scaffold, test harness, state, screen.
- **M2 Capture + collect**: capture, session mapping, cron denial check, collect (split), gate.
- **M3 Lessons + guard**: lessons, restore primitives, guard, applier, tick, dream skill,
  commands, installer. Ships in `shadow`.
- **M4 Wiki + memory**: wiki target, journal page, memory target (needs wiki-hint contract).
- **M5 Verify + heal**: verification runner, circuit breaker, heal, reports, multi-profile.
- **M6 Release**: docs, versioning, catalog listing, shadow -> autonomous switch, first live week.

Every issue has a `Depends:` line. `autonomous` may become the default only after restore
primitives, guard, verification runner and circuit breaker are merged and one shadow week shows
no vetoed or conflicting changes. The release depends on the memory target and therefore on
wiki-hint's memory-edit contract; that is intended.
