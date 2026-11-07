#!/usr/bin/env python3
"""One-off: review round 5 edits to the issues."""
import subprocess

R = "seppegadeyne/hermes-dream"


def gh(*a):
    r = subprocess.run(["gh", *a], capture_output=True, text=True)
    return (r.stdout or r.stderr).strip()


def body(n):
    return gh("issue", "view", str(n), "-R", R, "--json", "body", "--jq", ".body")


def save(n, b):
    print(n, gh("issue", "edit", str(n), "-R", R, "--body", b)[-30:])


def sub(n, pairs):
    b = body(n)
    for o, nw in pairs:
        if o not in b:
            print(n, "MISSING:", o[:60])
        b = b.replace(o, nw)
    save(n, b)


def deps(n, d):
    b = body(n).split("\n", 1)[1].lstrip("\n")
    save(n, f"Depends: {d}\n\n{b}")


def add(n, text):
    b = body(n)
    head, tail = b.split("\n\n---\n", 1)
    save(n, head + "\n\n" + text + "\n\n---\n" + tail)


add(21, "Round 5 checks: (16) `executions.db` `source` for scheduler (`builtin`) vs `cronjob run` / "
    "`hermes cron run` / dashboard (`direct`) and for a `trigger_job`-queued run; (17) "
    "`post_llm_call` fires once per turn, sees the ContextVar in its timeout thread, and the "
    "hash of the normalized fenced JSON block matches the one in the output file, incl. with a "
    "provider fallback; (18) `no_cache_check_fn` hides the dream tools from a parallel session.")
sub(4, [("and\n`post_llm_call` only for dream executions (execution id + sha256 of the response).",
         "and\n`post_llm_call` only for dream executions (execution id, sha256 of the normalized "
         "fenced JSON block, sha256 of the user message, job-definition hash at run time; reject "
         "when `manual_run_prompt`/`manual_run_at` is set).")])
sub(7, [("Plans are bound by the response hash from #4 (plan §4.4), not by a nonce. ", "")])
sub(9, [("`dream_read_skill(name)`", "`dream_read_skill(home, name)`"),
        ("`check_fn` and a\n  per-handler check", "`check_fn` wrapped in `tools.registry.no_cache_check_fn` and a\n  per-handler check"),
        ("- `pre_tool_call` hook:", "- `pre_tool_call` hook, also for every non-dream session: block `write_file`/`patch` into "
         "`plugin-data/hermes-dream/**`, `cron/output/<dream_id>/**`, the gate/tick scripts and the "
         "plugin dir (fixed resolved prefixes, no I/O).\n- In dream sessions:")])
sub(25, [("The payload carries the verbatim current text of every candidate target (prompts of jobs in `cron_prompt_include`, wiki pages under `dream_wiki_dir`, memory entries), screened and capped, so the agent never needs another read tool.",
          "The payload carries every candidate target as `targets[]` with `home` and numbered spans (`span_id`, `sha256`, screened text, `redacted` flag) per plan §11: prompts of jobs in `cron_prompt_include`, wiki pages under `dream_wiki_dir`; memory entries only once #32 is enabled.")])
sub(27, [("framed `## Response`\n  hashing to the value recorded by the `post_llm_call` hook (#4), job definitions unchanged\n  (§7.6). Else `forged_plan`; zero/several/malformed fenced blocks = `no_plan`.",
          "the normalized fenced JSON block of the framed `## Response` hashing to the value recorded "
          "by the `post_llm_call` hook (#4), recorded user-message and definition hashes equal to the "
          "installed ones (§7.6). Only `source == \"builtin\"` executions. Missing hook record or "
          "zero/several/malformed blocks = `no_plan`; hash or definition mismatch = `forged_plan`. "
          "Code fills `old` from the payload span (`span_id` + `sha256`); a redacted span is never "
          "valid. Install-hash comes from a test fixture here; #11 stores it for real."),
         ("successful dream execution (source scheduler or `hermes dream`\n  CLI),", "successful dream execution,")])
sub(28, [("#28 ships the tick with stub slots for heal and verify; #13 and #18 wire into them.",
          "#28 ships the tick with stub slots for heal and verify; #13 and #18 wire into them. The tick "
          "also owns the job-definition drift check on every run (plan §7.6: JOB_DEFINITION_FIELDS, "
          "script and SKILL.md contents).")])
sub(11, [("- Store the definition hash of both jobs (§7.6).",
          "- Store the definition hash of both jobs over `JOB_DEFINITION_FIELDS` plus gate/tick script "
          "and dream SKILL.md contents (§7.6); re-running install re-stores it after a legitimate edit.\n"
          "- `hermes dream run`: queues the dream job with `trigger_job` (runs as `builtin`).")])
sub(13, [("Skips dream job,", "Exposure and skill bindings via `_resolve_cron_enabled_toolsets` (fail closed on error). Skips dream job,")])
sub(12, [("journal page also there;", "journal page `<dream_wiki_dir>/journal-{year}-W{week}.md`;")])
sub(18, [("noise signatures", "exposure per plan §4.7 (one load per distinct session, dream/tick sessions ignored, at least one real job run); noise signatures")])
sub(19, [("eligible skills = agent-created local only;", "eligible skills = agent-created local skills bound only to cron jobs without terminal/code/MCP toolsets (plan §4.5);")])
deps(29, "#18, #19, #13, #9, #11")
deps(10, "#26, #19, #11, #29")
