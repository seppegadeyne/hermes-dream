#!/usr/bin/env python3
"""One-off: review round 4. Rewrites the bodies that had contradictory 'Round 3' notes, fixes
section numbers and edges, adds the upstream-PR notes."""
import re, subprocess

R = "seppegadeyne/hermes-dream"
W = "seppegadeyne/hermes-wiki-hint"
FOOT = ("\n\n---\nRead first: `AGENTS.md`, `docs/plan.md` (sections named above). Done means: "
        "tests green (`python3 -m unittest discover -s tests`), `hermes plugins doctor . --ci` and "
        "`hermes plugins validate .` green, CHANGELOG entry, plan updated if a decision changed, "
        "PR links this issue.")


def gh(*a):
    r = subprocess.run(["gh", *a], capture_output=True, text=True)
    return (r.stdout or r.stderr).strip()


def body(repo, n):
    return gh("issue", "view", str(n), "-R", repo, "--json", "body", "--jq", ".body")


def put(repo, n, deps, text, title=None, foot=FOOT):
    a = ["issue", "edit", str(n), "-R", repo, "--body", f"Depends: {deps}\n\n{text}{foot}"]
    if title:
        a += ["--title", title]
    print(n, gh(*a)[-40:])


def sub(repo, n, pairs):
    b = body(repo, n)
    for o, nw in pairs:
        b = b.replace(o, nw)
    print(n, gh("issue", "edit", str(n), "-R", repo, "--body", b)[-40:])


put(R, 21, "none", """Plan: §4.1, §4.4, §4.6, §4.7, §4.9, §7.6, §8.

In a throwaway `HERMES_HOME`, prove and write down in `docs/spike.md`, with evidence per item:
1. Exact `post_tool_call` status/error text of a cron approval denial (`approvals.cron_mode: deny`).
2. `ctx.current_cron_execution()` inside the pre_tool_call hook thread, plugin tool handlers and
   `post_llm_call`, also after context compression; `None` outside cron and for children.
3. A `.py` script in `scripts/` imports `cron.jobs` and calls `trigger_job`, `pause_job`,
   `update_job` during a tick; `_jobs_lock` reentrancy and its 30 s in-process fallback.
4. `trigger_job` on paused jobs, `paused_reason`, `repeat`, interval anchors, a concurrent
   operator pause (race).
5. `tools.skill_ledger.rollback_entry` non-interactively; `skill_manage(action=patch)` from a
   script: ledger entry, actor, `write_approval` staging and `pending_id`.
6. `register_command(..., argument_mode='text')` on one messaging platform; which home a
   handler resolves in a multi-profile gateway.
7. no_agent job: stdout delivery, empty stdout = silent, non-zero exit alert.
8. Job with `enabled_toolsets: [hermes-dream-ro, no_mcp]` and Tool Search `auto`: exact tool list
   (deferred plugin tools behind `tool_call`), and what happens when the plugin is disabled.
9. `check_fn` on plugin tools hides them from non-dream sessions.
10. `post_llm_call` sees the final response of a cron agent run; its sha256 equals the framed
    `## Response` in `cron/output/<job>/<ts>.md`; mapping file -> execution by
    `started_at..finished_at`.
11. A forged output file and a job edited through the `cronjob` tool are both detected (§4.4, §7.6).
12. Effective `agent.max_turns` for a cron job (there is no per-job field).
13. `on_skill_lifecycle` "loaded" fires for `skill_view`, cron `skills:` injection and slash
    commands (fields available).
14. Optional upstream: whether NousResearch/hermes-agent#138099 (cron failure-signal files) and
    #144901 (`turn_origin` in hooks) are merged; if so note how collect/hook can use them.
15. Idea from NousResearch/hermes-agent#77295: lessons in `references/lessons.md` next to a
    skill instead of a section in SKILL.md; check whether `skill_view` shows such files and
    whether that is a safer pitfall location (SKILL.md untouched). Recommend one.

Acceptance: `docs/spike.md` merged; plan corrected where reality differs.""",
    foot="\n\n---\nDone means: `docs/spike.md` merged; no code, tests or plugin.yaml needed for this issue.")

sub(R, 2, [("§7.3, §7.4", "§7.3, §7.5, §7.7"), ("plan §7.4", "plan §7.5")])
sub(R, 3, [("Plan: §7.4.", "Plan: §4.4, §7.5."),
           ("Round 3: also the pitfall slot validator (plan §4.4): charset allowlist, max 200 chars "
            "per slot, reject backticks, `!`, `${`, URLs, foreign paths and security vocabulary "
            "(approval, config, token, secret, env, sudo, curl, wget, ssh, chmod, `| bash`).",
            "Also the slot validator (plan §4.4): NFKC, allowlist charset `[letters digits space "
            ".,;:'()-]`, one line, max 200 chars, Unicode Cf/Mn/Co rejected, slot must name the "
            "cluster's tool/job/error type; then a blocklist second pass (backticks, `!`, `${`, "
            "URLs, foreign paths, security words incl. Dutch: geheim, wachtwoord, sleutel). "
            "Bypass tests: homoglyphs, zero-width, full-width, `-->`, markdown links, headings.")])
put(R, 4, "#2, #3, #21", """Plan: §4.1.

Hooks and fields exactly as in the §4.1 table: `api_request_error`; `post_tool_call` (failures, plus
status ok only for `side_effect_tools`); `on_skill_lifecycle` "loaded" (exposure, dream skill
excluded); `post_approval_response` (interactive); `subagent_stop`; `on_session_end`; and
`post_llm_call` only for dream executions (execution id + sha256 of the response). One O_APPEND
write per event, path from `get_hermes_home()` at event time, reuse the fingerprint from #2, daily
JSONL + rotation.

Acceptance: tests per hook with fake kwargs; a raising callback never propagates; timing well
under the dispatch timeout.""")
sub(R, 25, [("Define the payload schema", "The payload carries the verbatim current text of every candidate target (prompts of jobs in `cron_prompt_include`, wiki pages under `dream_wiki_dir`, memory entries), screened and capped, so the agent never needs another read tool. Define the payload schema")])
sub(R, 7, [("Write a per-run nonce to plugin state and include it in the gate output for the agent (plan §4.4).",
            "Plans are bound by the response hash from #4 (plan §4.4), not by a nonce.")])
put(R, 9, "#27", """Plan: §4.4.

- `skills/dream/SKILL.md`: read the payload and targets with the plugin tools (through `tool_call`
  when Tool Search defers them), check open lessons for opposite instructions, skip denylisted
  targets (report-only), return at most `max_applies` lessons as one fenced JSON block in the
  final response (schema §11). Skill lessons only as template slots. The skill's own examples
  contain no fenced json block.
- Plugin toolset `hermes-dream-ro`: `dream_read_payload()`, `dream_read_skill(name)`,
  `dream_read_lessons()`; names not paths; the `dream_read_skill` checks of §4.4; `check_fn` and a
  per-handler check that the caller is the dream execution.
- `pre_tool_call` hook: no I/O, `ctx.current_cron_execution()` vs cached dream job id,
  try/except -> None, blocks tools outside the toolset and after `dream_max_tool_calls`
  (a `tool_block` veto), always with a message.

Acceptance: hook timing < 1 ms; non-dream sessions untouched; tools invisible outside dream
sessions; traversal/symlink/hub tests for `dream_read_skill`.""",
    title="Dream skill, read-only toolset and write-blocking hook")
put(R, 27, "#19, #26, #7", """Plan: §4.4, §4.5, §7.6, §11.

- Authenticate the dream output: successful dream execution (source scheduler or `hermes dream`
  CLI), exactly one output file in its `started_at..finished_at` window, framed `## Response`
  hashing to the value recorded by the `post_llm_call` hook (#4), job definitions unchanged
  (§7.6). Else `forged_plan`; zero/several/malformed fenced blocks = `no_plan`.
- Track processed executions; code assigns `L-n`; screen every lesson (all targets); `guard.py`
  incl. "next attempt must differ"; skill pitfalls rendered by code; apply per the §4.5 table
  (wiki report-only until #12, memory until #32); staged skill write -> `waiting`; shadow records
  without writing.

Acceptance: golden tests (a apply part), (f); forged file, edited job and hash mismatch all
rejected; shadow writes nothing.""",
    title="Applier: authenticate the dream output, validate and apply per target")
put(R, 11, "#28, #9", """Plan: §4, §7.4, §7.6, §8.

wiki-hint `upkeep.py` pattern: find jobs by script name, create paused, update existing.
- Dream job: schedule `dream_schedule`, `enabled_toolsets: [hermes-dream-ro, no_mcp]`,
  `deliver: local`, pinned model (`model`, `provider`, `pinned: true`). Hermes has no per-job
  max_turns; the hook's `dream_max_tool_calls` is the budget.
- Tick job: `no_agent`, every 15 min, deliver `tick_deliver`.
- Store the definition hash of both jobs (§7.6).
- `--check`: toolset registered in this profile, effective `agent.max_turns`, warn on
  `cron_mode: approve`, refuse autonomous with `skills.inline_shell`, `WIKI_PATH`, wiki-hint
  presence and contract version, jobs with `context_from` on the dream job.
- `status` (shared with #10), `remove` (jobs, scripts, data with a flag).

Acceptance: idempotent install; dry-run writes nothing; remove leaves no job; one real dream
run on harness data in shadow.""")
put(R, 13, "#28, #5, #19", """Plan: §4.6.

- Retry only `retry_include` jobs, transient classes after >=1 API call, no successful
  `side_effect_tools` call, delivery failed/suppressed, enabled + scheduled + no live claim + no
  `quota_hold_until`, own `retry_delay_minutes`, `max_retries_per_day` (triggered verification
  runs included).
- Pause only `pause_include` jobs after `pause_after_failures` identical failures; creates `H-n`
  (job, `paused_at`, reason hash). Own pause = matching H-record, never the marker string alone.
- Resume our own pause with `trigger_job` (it un-pauses) when a lesson for that job reaches
  `verifying`; never `resume_job`. `closed_at` when resumed by us, changed by someone else, or
  deleted.
- Every trigger/pause is a compare-and-swap under `_jobs_lock` (re-read state, claim, H-record).
- Skips dream job, tick job, wiki-hint upkeep; retries skip jobs with an open lesson; shadow = no
  action; tick always exits 0.

Acceptance: golden test (c); never retry with 0 API calls, never twice a day, never an
operator-paused job; CAS race test.""")
put(R, 29, "#18, #19, #13", """Plan: §7.3, §7.7.

Veto classes `tool_block` (trips at `breaker_tool_blocks` per run), `denied_target`, `forged_plan`
(incl. job-definition drift), `screen_hit` (>= 2 in 7 days); plus rollback count/rate, heal actions
per day, corrupt state. Breaker events and paused flag in an append-only hash-chained log;
broken chain = trip. Reset only by `hermes dream resume` (CLI).

Acceptance: golden test (d); veto, forged, drift, corrupt-chain cases.""")
sub(R, 19, [("Round 3: veto classes `tool_block`, `denied_target`, `forged_plan`, `screen_hit` (plan §7.3); ",
             "Veto classes are implemented in #29. "),
            ("Plan: §7.1, §7.2, §7.4, §2.", "Plan: §2, §7.1, §7.2, §7.4, §7.5, §7.6.")])
sub(R, 26, [("memory restore is a separate later step once seppegadeyne/hermes-wiki-hint#5 is merged; until then memory lessons are report-only.",
             "memory restore is built in #32. Own-hunk revert: skills by marker block; wiki and cron prompts by replacing `new` with `old` when `new` occurs exactly once; else `conflict`.")])
sub(R, 17, [("§11", "§12")])
sub(R, 12, [("Round 3: write into `dream_wiki_dir`", "Only when wiki-hint with the untrusted-pages feature is enabled (else report-only); guard requires the resolved path under `dream_wiki_dir`; journal page also there; write into `dream_wiki_dir`")])
sub(R, 6, [("Read-only collectors;", "Read-only collectors (if NousResearch/hermes-agent#138099 is merged, read `cron/failures/<job>.json` first, fall back to own snapshot);")])

for n, d in [(25, "#23, #24, #8"), (16, "#11, #20, #29, #30, #12, #10, #32"), (17, "#29, #30, #16, #12, #32, #10")]:
    b = body(R, n).split("\n", 1)[1].lstrip("\n")
    print(n, gh("issue", "edit", str(n), "-R", R, "--body", f"Depends: {d}\n\n{b}")[-30:])

b = body(W, 7)
if not b.startswith("Depends:"):
    b = "Depends: none\n\n" + b
b = b.replace("wiki-hint must never inject them as hints",
              "wiki-hint must never inject them as hints (hints match `index.md` lines, so exclude index lines linking into the dream folder; no per-page frontmatter reads)")
print(gh("issue", "edit", "7", "-R", W, "--body", b)[-30:])
b = body(W, 6).replace("the upkeep wrapper script acquires before the agent run and releases after it (TTL covers the run).",
    "the upkeep gate script acquires before the agent run (a gate script exits before the agent starts, so it cannot release); release happens in a wiki-hint `on_session_end` hook keyed on `ctx.current_cron_execution().job_id`, and the TTL covers a crashed run.")
print(gh("issue", "edit", "6", "-R", W, "--body", b)[-30:])
b = body(W, 5)
if "upkeep.py" not in b:
    b = b.replace("- `--check` output", "- `hermes wiki-hint` subcommand dispatch (`upkeep.py` `handle()`) currently accepts only `upkeep`; widen it.\n- `--check` output")
print(gh("issue", "edit", "5", "-R", W, "--body", b)[-30:])
