# hermes-dream: implementation plan

Status: plan, nothing built yet. Every section maps to one or more GitHub issues; the issue is
the unit of work, this file is the shared design. Update this file in the same PR when a
decision changes.

## 1. Goal

A Hermes plugin that makes a Hermes setup smarter on its own: it turns yesterday's execution
into lessons, applies them, checks whether they helped and rolls back the ones that did not.
Failing cron jobs are healed during the day.

```
capture (hooks, always on, cheap)
  -> collect (nightly script, no LLM)
  -> gate (wake the agent only when there is work)
  -> dream (one agent turn: turn clusters into numbered lessons and apply them)
  -> verify (next days/runs: did the failure stop? otherwise automatic rollback)
  -> report (morning: what changed; weekly: what the system learned and whether it helped)
heal (every 15 min, no LLM): transient retry, pause on repeated failure
```

The "dreaming" idea comes from two places:

- the harness/loop pattern (agents that recover through logs, retry instead of restart, and
  turn past execution logs into new memories);
- the community plugin `hermes-dreaming` (itpartypattaya, MIT), which consolidates
  conversation facts into `MEMORY.md` with a deterministic nightly pass.

Hermes already covers parts of this and the plugin must not duplicate them:

| Built in | What it does | What it does not do |
|---|---|---|
| Background self-improvement review | After N turns, a fork re-reads the current conversation and saves memory or skill lessons | Never reads cron runs, errors.log, refused approvals or other sessions |
| Curator | Weekly prune of unused agent-created skills; optional LLM consolidation | Learns nothing new |
| `cron.retry_unreachable` | Re-runs a recurring job 5/15/30 min later when it failed before any model call (network/DNS) | Does not cover failures after the first API call (429, 5xx mid-run, tool crashes) |
| `/journey` | Timeline of saved memory and skills | View only |

hermes-dream fills the gap: learning from **execution** (crons, tool errors, blocked
approvals, subagent failures) across **all sessions and profiles**, autonomously with
guardrails, and
writing durable knowledge to an **llm-wiki** vault as well as to skills and memory.

## 2. Autonomy and non-goals

The system runs **fully autonomously**: it detects, decides, applies, verifies and rolls back on
its own. The operator is informed after the fact (morning report) and can veto or roll back any
change, but nothing waits for a "yes". Safety comes from guardrails (section 4.8), not from a
human gate:

- every change is reversible and recorded with its before-state;
- every change has a verification window and is rolled back automatically when it did not help
  or made things worse;
- a hard denylist of targets the system may never touch;
- caps per night and a global kill switch.

Non-goals:
- No fact store / vector DB / memory provider. The memory slot stays as the operator set it.
- No cloud judge and no network calls from the scripts. The only model call is the agent turn
  in the nightly cron job, on the operator's configured model.
- No re-implementation of the curator, the background review or `cron.retry_unreachable`.

## 3. Ideas borrowed from hermes-dreaming (MIT, credited in README)

Take the design, write our own code (the domain is different: execution, not facts).

1. Deterministic pass first, model second; the script never writes curated stores.
2. Wake gate: the job's script prints `{"wakeAgent": false}` on a quiet night, so no model
   turn starts.
3. Corroboration: a lesson counts only when its signal repeats (N occurrences or on distinct
   days). Machine-only text (cron prompts, compaction banners, the plugin's own runs) never
   corroborates anything.
4. Every item gets an outcome: applied, rejected (with reject list + `--undo`), or it returns
   after a cooldown. Nothing is asked forever; cooldowns start only when a proposal was
   actually shown.
5. Immutable proposal numbers (`L-17`), text fingerprints instead of database ids.
6. Caps per night (e.g. max 5 proposals, max 3 applies); zero proposals is a success.
7. (Moved to wiki-hint, see section 9: loss guard, memory pressure, "still relevant?" decay
   questions and approval-queue awareness for `MEMORY.md`/`USER.md`.)
8. Screening: secrets and prompt-injection phrasing are quarantined before anything reaches
   the proposal, the report, the wiki or the model. Regex screen, documented as "not a
   guarantee".
9. Robust state: atomic writes (temp file + rename), a corrupt state file is moved aside to
   `<file>.corrupt-<utc>` and never read as "empty", one state lock.
10. Installer with `--dry-run`, `--check`, idempotent cron creation found by script name,
    created paused, and prompt sync that preserves operator-edited prompts.
11. Respect Hermes' approval queue for this plugin's own apply step: a `skill_manage` write
    staged by `skills.write_approval` counts as "waiting", not "applied". (The memory side of
    the queue belongs to wiki-hint, section 9.1.)

Not borrowed: holographic fact store, cloud judge, multi-language stemming tables.

## 4. Architecture

```
hermes-dream/
  plugin.yaml            manifest v2, provides_hooks, config_schema, requires_hermes
  __init__.py            register(ctx): hooks, /dream command, `hermes dream` CLI
  capture.py             hook callbacks -> event journal (metadata only)
  collect.py             nightly deterministic pass -> payload JSON (no LLM, no writes to curated stores)
  screen.py              secret / injection screen
  state.py               atomic JSON state, lock, corrupt-aside, fingerprints
  proposals.py           numbering, cooldowns, reject list, outcomes
  install.py             cron jobs + gate wrapper, --dry-run/--check/remove (copy wiki-hint's upkeep.py pattern)
  skills/dream/SKILL.md  the procedure the nightly agent and the review turn follow
  tests/                 stdlib unittest, offline, fixtures with fake state.db / executions.db
```

Runtime data lives in `ctx.state.data_dir` (keyed by plugin id `hermes-dream`; outside
`register()` use `plugin_data_dir("hermes-dream")`), never in the plugin directory (updates
replace it). There is no `wiki.py`: wiki writes are an agent step that follows the llm-wiki skill
and the vault's `SCHEMA.md`.

### 4.1 Capture (hooks)

Observer hooks, fail-open, constant time, metadata only (no prompts, no tool results, no
arguments beyond names and bounded targets):

| Hook | Recorded when |
|---|---|
| `api_request_error` | always: status_code, retryable, retry_count, provider, model, reason class |
| `post_tool_call` | `status` in error/blocked/cancelled: tool name, error_type, first 200 chars of error_message after screening |
| `post_approval_response` | interactive sessions only: choice in deny/timeout/cancelled, pattern_key, surface. Cron denials under `approvals.cron_mode: deny` do NOT fire this hook (`tools/approval.py` `_unattended_deny`); they surface as a blocked/error `post_tool_call`, recognised by the block-message text (verify the exact text with a real cron deny first) |
| `subagent_stop` | `child_status` not ok: `child_role`, `duration_ms`, outcome counts derived from `tool_call_history` |
| `on_session_end` | `failed` or `interrupted` true, plus `turn_exit_reason`; fires per conversation run, not per session identity, and not for background-review forks |

`api_request_error` fields: `status_code`, `retryable`, `retry_count`, `reason`, `error.type`,
`provider`, `model` (no separate "overload" class: classify from these).

Each event: `ts, profile, session_id, platform, job_id, kind, signature`. `platform` is
`"cron"` for cron runs; `job_id` comes from the cron session id prefix `cron_<jobid>_<ts>`.

Hard performance rule: these hooks run under a dispatch timeout and are suppressed for 60 s
after one (`hermes_cli/plugins_dispatch.py`); `subagent_stop` runs on the caller's thread. The
journal append is one `write()` of one line with `O_APPEND`, no lock wait, no I/O beyond that.
Resolve the journal path from `get_hermes_home()` at event time (one gateway process serves
several profile homes), never cache it at registration. The signature normalizes numbers, ids, paths and hashes so the same
failure groups across runs. Append-only JSONL per day, rotated after `retention_days`
(default 30).

Rationale: `state.db` already holds sessions, but extracting tool errors from it afterwards is
expensive and lossy; a tiny journal written at the source is cheap and precise. The collect
pass still reads `state.db` / `executions.db` for history before the plugin was installed.

### 4.2 Collect (nightly, deterministic)

Inputs, read-only (SQLite `mode=ro`):

- event journal of the last 24 h (and the corroboration window, default 14 days);
- `cron/executions.db`: failed/unknown runs, error text, delivery_outcome;
- `cron/jobs.json`: failure streaks, paused jobs without reason, jobs referencing missing
  skills;
- `logs/errors.log`: WARNING/ERROR lines grouped by normalized signature;
- `state.db`: refused approvals and tool errors before the journal existed (first run only);
- what Hermes already learned, so proposals do not repeat it: the skill write ledger
  `skills/.curator_ledger.jsonl` (every skill_manage/background-review write, with content
  hashes), curator runs `logs/curator/*/run.json`, and a diff of `MEMORY.md` (the agent.log
  "Background review complete" line names only the kind of write, not its content);
- note: `state.db` does not record cron approval denials, so the first-run backfill cannot
  find them; only the journal does from install onwards;
- optional: every profile home (`--homes all`), same as one-install multi-profile setups.

Output: `payload.json` with candidate clusters. Each cluster: signature, count, distinct days,
first/last seen, affected jobs/tools/skills, 1-3 screened evidence snippets with their source
(file:line or session id + message id), and a suggested target class:

| Target | Example |
|---|---|
| `skill` | the same tool error recurs in sessions that loaded skill X -> pitfall for X |
| `cron` | a job fails the same way 3 nights -> prompt or schedule change, or pause |
| `wiki` | a durable finding (procedure, root cause, decision) -> wiki page or log entry |
| `memory` | an environment fact that applies to every session (rare; strict) |
| `retry` | a transient failure after the first API call on a job marked idempotent |
| `noise` | a recurring warning that is harmless -> propose a known-noise entry |

### 4.3 Gate

Gate wrapper (written by the installer to `<HERMES_HOME>/scripts/dream_gate.sh`; cron only runs
scripts inside that folder) calls system `python3` on the plugin's `collect.py`, same pattern as
wiki-hint's `upkeep.py` wrapper, so it survives plugin updates. It prints `{"wakeAgent": false}`
when there is no cluster above threshold, no open proposal waiting and no state alert. Otherwise
it prints only the payload path and a one-line summary: stdout is pasted into the prompt and
goes through the injection scanner, so evidence never travels via stdout. Empty stdout skips the
run silently, so the wrapper always prints one of the two. With `homes: all` the installer
creates one job per profile.

### 4.4 Dream (agent turn: decide and apply)

Cron job bound to skill `hermes-dream:dream` (plugin skills are namespaced by manifest name),
`enabled_toolsets` limited to file and skills. The run is unattended (`approvals.cron_mode`
applies), so it must not need flagged commands; the installer `--check` warns about the mode. The agent:

1. reads the payload;
2. for each cluster, reads the referenced skill/wiki page/cron prompt to check whether the
   lesson is already there (no duplicate proposals);
3. writes at most `max_proposals` numbered proposals, each with: what happened (evidence),
   the exact change (verbatim old/new text or a new section), the target path, risk, and how
   to verify it worked;
4. ends with a short report delivered to the operator's channel.

It then applies the changes itself (section 4.5), within the caps and guardrails, and records
each one as an open "lesson under verification". The proposal format stays: it is the change
record used for verification, rollback and the report.

### 4.5 Apply (autonomous) and operator override

The nightly agent applies changes directly through the paths below. The operator never has to
answer, but can intervene in chat: `/dream show` (open lessons), `/dream undo L-17` (roll back
now), `/dream block L-18 <reason>` (roll back and never retry this signature), `/dream pause`.
These overrides need no agent: the handler restores the saved before-state itself (same code as
the automatic rollback, section 4.8) and updates state, so they work in every gateway session
without `allow_gateway_injection`. Register the command with an args hint and text argument
mode so Telegram/Discord pass the rest of the line. The same actions exist on the CLI
(`hermes dream undo|block|pause|resume|status`).

The nightly agent applies through the normal paths:

- skill: `skill_manage patch` (ledgered, respects `skills.write_approval`, curator can roll back);
- memory: `memory` tool `patch`/`add` (respects `memory.write_approval`);
- wiki: the llm-wiki procedure (section 5);
- cron: `hermes cron edit` for prompt/schedule, or pause with a reason;
- retry: `cron.jobs.trigger_job(id)` once (sets `next_run_at`; the scheduler's normal claim
  prevents double runs; note it also un-pauses a paused job). Never shell out to
  `hermes cron run`, which runs the whole job synchronously in the calling process.

"no" adds the fingerprint to the reject list with the reason; a rejected signal comes back
only if it reappears after `reject_reask_days` (default 90).

### 4.6 Self-healing: retry and replay (the "recover instead of restart" part)

A separate `no_agent` heal job runs every 15 minutes (no model, no cost). It reads
`cron/executions.db` and the journal and acts on fresh failures of recurring jobs:

- transient failures (429, 5xx, timeout, provider overload) after at least one API call: one
  re-run via `trigger_job` after `retry_delay_minutes`;
- side-effect safety: no re-run when the failed session already made a successful call to a
  sending or mutating tool (send_message, email/MCP send tools, terminal commands, `gh` writes,
  browser form submits; list in settings `side_effect_tools`), or when the job is in
  `retry_exclude`; those become a lesson for the nightly run instead;
- a job that failed the same way `pause_after_failures` times in a row (default 3) is paused
  with `paused_reason` set by the plugin, and listed in the report; the nightly run tries a fix
  and resumes it when the fix is applied;
- every heal action is logged and verified like any other change.

Former limits that still hold:
- only failures classified transient for the re-run itself (HTTP 429, 5xx, provider overload, timeout) that
  `cron.retry_unreachable` does not already handle;
- never when the failed run made zero API calls (that is `cron.retry_unreachable`'s case; test it);
- at most one re-run per job per day, delayed `retry_delay_minutes` (default 20), via `trigger_job`;
- every re-run is logged and appears in the morning report.

Everything else goes to the nightly dream run as a lesson. "Replay" means: every lesson links
the failed execution (execution id, session id, output file) so the agent resumes from the
evidence instead of starting over; when the nightly run fixed a job, it triggers one re-run of
that job (`trigger_job`) as the first verification.

### 4.8 Guardrails, verification and automatic rollback

This replaces the human gate. Every applied change ("lesson") goes through the same lifecycle:

```
detected -> applied (before-state saved) -> verifying (N days) -> kept | rolled back
```

1. **Before-state**: skill writes go through `skill_manage` (ledgered; single-entry rollback with
   `hermes curator rollback <entry-id>`); cron prompt/schedule changes save the old job fields in
   the plugin state; wiki writes are recorded as file + sha256 before/after; memory writes go
   through wiki-hint's locked `memory_edit.py` (backup per write) when installed, otherwise the
   `memory` tool with the old text saved.
2. **Verification window** (`verify_days`, default 3; for jobs: the next `verify_runs` runs,
   default 3): the signature that triggered the lesson must drop (fewer occurrences than before,
   and zero for job failures), and no **new** failure signature may appear in the same target
   (same job, same skill's sessions, same tool).
3. **Automatic rollback** when verification fails or a regression appears: restore the
   before-state, mark the signature "tried: <change>" so the next attempt must be different,
   and after `max_attempts` (default 2) failed fixes the signature is escalated: listed in the
   report as "needs a human", the job stays paused if it was paused, no further attempts.
4. **Kept** lessons stay; the weekly report lists them with before/after counts.
5. **Denylist** (hard-coded, not configurable away): `SOUL.md`, `config.yaml` and `.env` of any
   home, credentials and `~/.secrets`-style paths, plugin code (including this plugin), Hermes
   source, `USER.md`, other repositories, deleting skills or wiki pages, deleting cron jobs,
   anything that sends messages or mail on its own. Proposals for those are report-only.
6. **Caps**: per night `max_applies` (default 5), per target one change per verification
   window (no stacking changes on the same skill/job before the first is verified), heal job
   `max_retries_per_day`.
7. **Circuit breaker**: if more than `breaker_rollbacks` (default 3) rollbacks happen in 7 days,
   the plugin stops applying (detect + report only) until `hermes dream resume`.
8. **Kill switch**: `hermes dream pause` / `/dream pause` stops both jobs immediately.
9. **Transparency**: every action lands in the morning report (delivered to the operator's
   channel) and in the weekly wiki journal, with a ready `/dream undo L-n`.

`mode` setting: `autonomous` (default, everything above), `shadow` (detect and write lessons as
proposals but apply nothing; for trying it on a new install), `off`.

### 4.7 Weekly report

Once a week: lessons applied / kept / rolled back / escalated, heal actions (retries, pauses,
resumes), top recurring signatures, and for kept lessons the before/after counts. Headline
metric: failed cron runs and tool errors per week, trending down. This is the measurement that
shows whether the setup really gets smarter on its own.

## 5. llm-wiki integration

Scope: hermes-dream only **adds** lessons to the vault (journal page, applied lessons). Vault
upkeep belongs to wiki-hint (section 9.1); do not add audit or repair logic here.

Target: an Obsidian/llm-wiki vault at `WIKI_PATH` (same env var as the `wiki-hint` plugin) that
has `SCHEMA.md`, `index.md` and `log.md`.

Rules (mirror the llm-wiki conventions; read the vault's `SCHEMA.md` at runtime and follow it):

- Before writing, read `SCHEMA.md`, `index.md` and the tail of `log.md`.
- Dream diary: one page per ISO week, `queries/dream-journal-YYYY-Www.md` (path configurable),
  frontmatter per schema (`type: query`, tags from the vault taxonomy, `sources` = evidence
  references). Created only when there is at least one proposal that week.
- Applied wiki lessons: update the existing page when one matches (bump `updated`), otherwise
  create a new page and add it to `index.md` under the right section.
- Every wiki write appends one line to `log.md` in the vault's format.
- Evidence stays as references in `sources` (execution id, session id, log file:line); no
  copies in `raw/` (raw hashes are wiki-hint upkeep territory).
- Use existing taxonomy tags only. A missing tag is left for the wiki-hint upkeep, which adds
  tags by its own rule (used on 2+ pages).
- If `WIKI_PATH` is unset or the schema files are missing, wiki targets are reported as
  "unavailable" and the rest keeps working.

## 6. Settings (`config_schema`, read with `ctx.get_config`)

| Key | Default | Meaning |
|---|---|---|
| `homes` | `current` | `current` or `all` (every profile of this install) |
| `window_days` | 14 | corroboration window |
| `min_occurrences` | 3 | cluster threshold (or `min_days`) |
| `min_days` | 2 | distinct days threshold |
| `max_proposals` | 5 | per night |
| `mode` | `autonomous` | `autonomous`, `shadow` (proposals only) or `off` |
| `max_applies` | 5 | changes per night |
| `verify_days` | 3 | verification window for skill/wiki/memory lessons |
| `verify_runs` | 3 | verification window (runs) for cron lessons |
| `max_attempts` | 2 | different fixes per signature before escalation |
| `breaker_rollbacks` | 3 | rollbacks in 7 days that stop applying |
| `pause_after_failures` | 3 | identical consecutive job failures before the heal job pauses it |
| `side_effect_tools` | send_message, terminal, ... | tools whose successful call blocks an automatic re-run |
| `retry_exclude` | `[]` | job ids never re-run automatically |
| `max_retries_per_day` | 1 | per job |
| `cooldown_days` | 3 | before a deferred lesson is reconsidered |
| `reject_reask_days` | 90 | after `/dream block`, or after escalation |
| `retention_days` | 30 | event journal |
| `retry_delay_minutes` | 20 | |
| `wiki_journal_path` | `queries/dream-journal-{year}-W{week}.md` | |
| `deliver` | job default | delivery target for the morning report |
| `language` | `en` | report language (`en`, `nl`) |

## 7. Safety

- All reads of Hermes databases are `mode=ro`.
- The capture hooks never raise; any exception is swallowed after one log line per hour.
- Screening before anything leaves the journal (proposal, report, wiki, model context).
- Caps per night, kill switch `hermes dream pause`, and `hermes dream status`.
- The plugin never deletes curated content, cron jobs or pages; rollbacks restore before-states.
- Guardrails, denylist, verification and circuit breaker as in section 4.8.
- Public repo: no private paths, hostnames, names or tokens in code, tests, docs or fixtures.

## 8. Manifest

`manifest_version: 2`, `kind: standalone`, `requires_hermes` (oldest release with every surface
used: `inject_message`, `register_skill`, `register_command`, `register_cli_command`,
`ctx.state`, observer hooks; check per tag), `provides_hooks` listing every registered hook,
`config_schema` for section 6, `license`, `homepage`. Detect wiki-hint with `ctx.has_plugin()`.

## 8b. Testing

- stdlib `unittest`, offline, no Hermes import for unit tests (load modules by path, fake ctx).
- Fixtures: tiny generated `state.db`, `executions.db`, `jobs.json`, `errors.log`, a fake wiki
  vault with `SCHEMA.md`/`index.md`/`log.md`.
- Golden tests: (a) a recurring failure -> lesson applied -> signature drops -> kept;
  (b) lesson applied -> signature persists -> rollback -> second, different fix -> escalation;
  (c) heal job: transient 429 -> one re-run; side-effect tool already called -> no re-run;
  3 identical failures -> pause; (d) circuit breaker trips after N rollbacks;
  (e) denylisted target is never written.
- `hermes plugins doctor . --ci` and `hermes plugins validate .` in CI.

## 9. Coexistence and division of labour

### 9.1 wiki-hint owns the wiki and the always-loaded memory files

[wiki-hint](https://github.com/seppegadeyne/hermes-wiki-hint) (same author) already ships a
weekly upkeep cron (`maintenance.py` audit, `MAINTENANCE.md` playbook, `memory_edit.py` as the
only locked write path for `MEMORY.md`/`USER.md`). hermes-dream does **not** rebuild any of it.

| Concern | Owner | Notes |
|---|---|---|
| Wiki hygiene: index, broken links, frontmatter, tags, page size, `log.md` rotation, `raw/` hashes | wiki-hint | hermes-dream never audits or repairs the vault |
| Memory pressure (85% target), near-duplicate entries, entries naming missing paths | wiki-hint | already in `maintenance.py` |
| Unattended writes to `MEMORY.md` | wiki-hint `memory_edit.py` | hermes-dream's nightly run calls it (locked, backed up) when wiki-hint is installed; `USER.md` is denylisted |
| Backups of vault and memory before edits | wiki-hint | |
| Loss guard (memory shrank overnight) | wiki-hint (new issue) | idea from hermes-dreaming |
| "Still relevant?" questions for old memory entries, with cooldowns | wiki-hint (new issue) | idea from hermes-dreaming |
| Approval-queue awareness (`pending/memory`: staged = waiting) | wiki-hint (new issue) | idea from hermes-dreaming |
| Execution capture (hooks), collect, clustering, autonomous apply, verification, rollback, self-healing heal job, weekly learning report | hermes-dream | |
| New durable lessons that belong in the wiki | hermes-dream writes them autonomously following the vault's `SCHEMA.md` | the next wiki-hint upkeep run then audits those pages like any other |

The new wiki-hint items are filed as issues on the wiki-hint repo, not built here.

hermes-dream must still work without wiki-hint (public plugin): it then simply leaves wiki and
memory hygiene uncovered and says so in `hermes dream status`. It detects wiki-hint by plugin
id (enabled plugin list), never by path, and shares only the `WIKI_PATH` env var.

Schedule: the dream job runs nightly; wiki-hint's upkeep runs weekly. Keep them apart in time
(dream at night, upkeep on its own slot) so the upkeep audits pages the dream applied that week.

### 9.2 Hermes built-ins

- Background review and curator: collect reads their recent outcomes and drops clusters that
  were already turned into a lesson.
- `cron.retry_unreachable`: the retry step skips failures with zero API calls.

## 10. Milestones

- **M1 Foundation**: scaffold, state, screen, CI.
- **M2 Capture + collect**: hooks, journal, collectors, payload, gate.
- **M3 Dream + apply**: skill, lessons, autonomous apply paths, `/dream` overrides, installer.
- **M4 Wiki**: journal page, apply-to-wiki.
- **M5 Self-heal + verify**: heal job (retry, pause, resume), verification, automatic rollback,
  circuit breaker, replay links, weekly report.
- **M6 Release**: docs, catalog-ready validation, first live week.

Release order: M5's verification and rollback must be merged before `mode: autonomous` is the
default; until then builds ship with `mode: shadow`. The first live week runs autonomous with
the guardrails; its report (applied, kept, rolled back) is the acceptance test.
