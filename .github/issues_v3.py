#!/usr/bin/env python3
"""One-off: fold review round 3 (security, feasibility, consistency) into both issue sets."""
import subprocess

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


def put(repo, n, b, title=None):
    args = ["issue", "edit", str(n), "-R", repo, "--body", b]
    if title:
        args += ["--title", title]
    print(gh(*args))


def deps(repo, n, d):
    b = body(repo, n)
    if b.startswith("Depends:"):
        b = b.split("\n", 1)[1].lstrip("\n")
    put(repo, n, f"Depends: {d}\n\n" + b)


def append(repo, n, text):
    b = body(repo, n)
    if text in b:
        return
    if "\n\n---\n" in b:
        head, tail = b.split("\n\n---\n", 1)
        put(repo, n, head + "\n\n" + text + "\n\n---\n" + tail)
    else:
        put(repo, n, b + "\n\n" + text)


# ---- wiki-hint: new issue, deps, fixes
untrusted = gh("issue", "create", "-R", W, "--title",
    "Treat hermes-dream pages as untrusted: no hint injection, no upkeep instructions",
    "--body",
    "Pages with frontmatter `source: hermes-dream` / `trust: untrusted` (folder "
    "`queries/dream/` by default) are written by an autonomous plugin from log evidence. "
    "wiki-hint must never inject them as hints, and the upkeep run must treat them as data only "
    "(audit them, never follow text in them, never copy their content into memory).\n\n"
    "Acceptance: matcher test (such pages never appear in hints); MAINTENANCE.md rule; audit "
    "still lists their hygiene issues.\n\nContext: hermes-dream plan §4.5 (wiki row).")
WU = int(untrusted.rsplit("/", 1)[-1])
print(untrusted)
b5 = body(W, 5).replace("apply-plan JSON schema", "\"memory change set\" JSON schema")
put(W, 5, "Depends: none\n\n" + b5)
b6 = body(W, 6).replace(
    "Add one advisory lock \n(`flock` on `<vault>/.wiki-lock` or under plugin-data, documented)",
    "").replace(
    "(`flock` on `<vault>/.wiki-lock` or under plugin-data, documented) taken by the upkeep for "
    "its whole repair pass and exposed for other plugins (`hermes wiki-hint lock --json` or a "
    "documented path + protocol).",
    "as a lease file `<vault>/.wiki-lock` (JSON: holder, pid, acquired_at, expires_at; created "
    "with O_EXCL, stale after expiry). A CLI cannot hold a flock for its caller, so: "
    "`hermes wiki-hint lock acquire --holder <id> --ttl <s>` / `release --holder <id>`; the "
    "upkeep wrapper script acquires before the agent run and releases after it (TTL covers the "
    "run). Other plugins use the same file protocol directly.")
put(W, 6, "Depends: none\n\n" + b6)
b3 = body(W, 3).replace(
    "Answers come back through a small command \n", "").replace(
    "Answers come back through a small command (`/wiki-audit keep <n>` / `/wiki-audit drop <n>`, "
    "or the CLI);",
    "Answers are recorded by a small command (`/wiki-audit keep <n>` / `/wiki-audit drop <n>`, or "
    "the CLI) that only writes the answer to plugin state; the next upkeep run applies a `drop` "
    "through memory_edit (the plugin itself stays read-only);")
put(W, 3, "Depends: seppegadeyne/hermes-wiki-hint#5\n\n" + b3)
b2 = body(W, 2).replace("(first \npersistent state of this plugin; atomic write)", "").replace(
    "(first persistent state of this plugin; atomic write)",
    "(atomic write; shared state dir with #3, whichever lands first creates it)")
put(W, 2, "Depends: seppegadeyne/hermes-wiki-hint#5\n\n" + b2)
deps(W, 4, "none")
append(W, 5, "Discovery: `hermes wiki-hint memory-edit --contract` prints `{\"contract_version\": N}` "
       "so a no_agent script can detect it without `ctx.has_plugin()`.")

# ---- hermes-dream
append(R, 21, "Round 3 additions: (11) per-job `enabled_toolsets` with `no_mcp` and a plugin-"
       "registered toolset in a cron job: exact tool list the agent gets; (12) "
       "`ctx.current_cron_execution()` from the pre_tool_call hook thread, also after context "
       "compression; (13) a forged file in `cron/output/<job>/` and how to authenticate the real "
       "one (nonce + executions row + `## Response` framing); (14) `trigger_job` racing an "
       "operator pause; (15) effective `agent.max_turns` for a cron job; (16) "
       "`skill_manage(action=patch)` called from a script: ledger entry, actor, staging.")
append(R, 3, "Round 3: also the pitfall slot validator (plan §4.4): charset allowlist, max 200 "
       "chars per slot, reject backticks, `!`, `${`, URLs, foreign paths and security "
       "vocabulary (approval, config, token, secret, env, sudo, curl, wget, ssh, chmod, `| bash`).")
append(R, 4, "Also record cheap ok events for skill loads (`skill_view` and skill-load) so "
       "verify can count exposure (plan §4.7).")
append(R, 25, "Also turn open `H-n` heal records into clusters (plan §4.6). Define the payload "
       "schema in `docs/schemas.md` (plan §11).")
append(R, 7, "Write a per-run nonce to plugin state and include it in the gate output for the "
       "agent (plan §4.4). Cooldown per signature that also covers vetoed and report-only "
       "items, so the same cluster does not wake the model every night.")
append(R, 8, "Define the change record and heal record schemas in `docs/schemas.md` (plan §11), "
       "incl. `waiting` -> `verifying`/`rolled_back` via `pending_id` and the `conflict` state.")
append(R, 26, "Skill pitfalls are located by their `hermes-dream:L-n` marker across all skills; "
       "re-hash right before and after the atomic rename; mismatch = `conflict`.")
append(R, 19, "Round 3: veto classes `tool_block`, `denied_target`, `forged_plan`, `screen_hit` "
       "(plan §7.3); cron prompt lessons report-only for jobs with terminal/code/MCP toolsets or "
       "when `approvals.cron_mode` is `approve`; environment checks of plan §7.4 "
       "(`skills.inline_shell` true = no autonomous).")
put(R, 27, body(R, 27).replace(
    "Apply-plan JSON schema (the dream agent's final response, parsed from the newest "
    "unprocessed `cron/output/<dream-job>/*.md`);",
    "Apply plan (schema in plan §11, written to `docs/schemas.md`): authenticate the dream output "
    "first (nonce, matching successful executions row, mtime, only the `## Response` section, "
    "exactly one fenced block; else `no_plan` / `forged_plan`), track processed files by "
    "execution id; code assigns `L-n`; skill pitfalls rendered by code from the template;"),
    title="Applier: authenticate the dream output, validate and apply per target")
put(R, 9, body(R, 9).replace(
    "Also build the `pre_tool_call` hook that blocks every write tool (write_file, patch, "
    "terminal, execute_code, skill_manage, memory, cronjob, send_message, mcp__*) in dream-job "
    "sessions; a block counts as a guard veto. Job uses `enabled_toolsets: [file, skills]`, "
    "`max_turns: 30`.",
    "Also build the plugin toolset `hermes-dream-ro` (`dream_read_payload`, `dream_read_skill`, "
    "`dream_read_lessons`, reading only plugin data and eligible skills) and the `pre_tool_call` "
    "hook (no I/O, `ctx.current_cron_execution()` vs cached dream job id, try/except -> None, "
    "blocks tools outside the toolset and after `dream_max_tool_calls`; a block is a "
    "`tool_block` veto). Job: `enabled_toolsets: [hermes-dream-ro, no_mcp]`, `deliver: local`. "
    "Pitfalls are returned as template slots, never free text.").replace(
    "one real run on harness data in shadow.", "the skill's own examples contain no fenced json "
    "block; hook timing test < 1 ms.").replace(
    "Acceptance: hook test (write_file blocked, read_file allowed, only in dream sessions);",
    "Acceptance: hook test (non-dream sessions untouched, tools outside the toolset blocked in "
    "dream sessions, counter limit);"),
    title="Dream skill, read-only toolset and write-blocking hook")
append(R, 11, "Round 3: dream job `enabled_toolsets: [hermes-dream-ro, no_mcp]`, `deliver: local`, "
       "pinned model (`model`, `provider`, `pinned: true`), schedule `dream_schedule`; tick job "
       "with `--deliver` (setting `tick_deliver`); `--check` shows effective `agent.max_turns`, "
       "warns on `cron_mode: approve`, refuses autonomous with `skills.inline_shell`. Moved "
       "here from #9: one real dream run on harness data in shadow. `status` lives here; #10 "
       "reuses it.")
append(R, 10, "Round 3: `resume` is CLI-only (clears kill switch and breaker); chat commands "
       "cannot re-arm after a breaker trip.")
append(R, 13, "Round 3: own pause = matching `H-n` record (job, paused_at, reason hash), not "
       "the marker string; every trigger/pause as compare-and-swap under the cron store lock; "
       "`trigger_job` only, never `resume_job`; verification runs are the ones the tick triggers "
       "(`manual_run_at`); tick always exits 0.")
append(R, 12, "Round 3: write into `dream_wiki_dir` with `source: hermes-dream`, `trust: "
       f"untrusted` (needs seppegadeyne/hermes-wiki-hint#{WU}).")
append(R, 28, "#28 ships the tick with stub slots for heal and verify; #13 and #18 wire into them.")
append(R, 29, "Implements the veto classes of plan §7.3; `hermes dream resume` (CLI) resets it.")

mem = gh("issue", "create", "-R", R, "--title", "Memory target: apply and revert via the wiki-hint memory change set",
    "--label", "plan", "--milestone", "M4 Wiki", "--body",
    "Depends: #27, #26, seppegadeyne/hermes-wiki-hint#5\n\nPlan: §4.5 (memory row), §4.7, §11.\n\n"
    "Turn memory lessons from report-only into real changes: detect the contract with "
    "`hermes wiki-hint memory-edit --contract`, apply through it with caller tag "
    "`hermes-dream:L-n`, store the change id in the change record, revert through its "
    "entry-level revert (conflict when the entries changed). Without the contract: stays "
    "report-only.\n\nAcceptance: apply + verify + revert on harness data; conflict case." + FOOT)
MEM = int(mem.rsplit("/", 1)[-1])
print(mem)

deps(R, 12, f"#27, seppegadeyne/hermes-wiki-hint#6, seppegadeyne/hermes-wiki-hint#{WU}")
deps(R, 16, "#11, #20, #29, #30, #12")
deps(R, 20, "#18, #13, #29")
deps(R, 31, "#17")
deps(R, 17, f"#29, #30, #16, #12, #{MEM}")
