#!/usr/bin/env python3
"""One-off: fold the final review into the issues (deps, spike items, write-block hook, report sending)."""
import subprocess

R = "seppegadeyne/hermes-dream"


def gh(*a):
    r = subprocess.run(["gh", *a], capture_output=True, text=True)
    return (r.stdout or r.stderr).strip()


def body(n):
    return gh("issue", "view", str(n), "-R", R, "--json", "body", "--jq", ".body")


def edit(n, fn):
    b = body(n)
    nb = fn(b)
    if nb != b:
        print(gh("issue", "edit", str(n), "-R", R, "--body", nb))
    else:
        print(n, "unchanged")


def set_deps(deps):
    def f(b):
        first, rest = b.split("\n", 1)
        return "Depends: " + deps + "\n" + rest
    return f


def add(text, after="\n\nAcceptance:"):
    def f(b):
        return b.replace(after, "\n\n" + text + after, 1) if text not in b else b
    return f


# spike: own done-criteria, two extra items
edit(21, lambda b: b.replace(
    "(7) a no_agent job's \"\n  \"output and wake behaviour.", "") .replace(
    "(7) a no_agent job's output and wake behaviour.",
    "(7) a no_agent job's stdout delivery and silent run on empty stdout; (8) a skill write "
    "through Hermes' skill API from a no_agent script: ledger entry and `skills.write_approval` "
    "staging; (9) a `pre_tool_call` hook can block `write_file`/`patch` for one cron job's "
    "sessions while `read_file` works; (10) the final response of a cron agent lands in "
    "`cron/output/<job>/<ts>.md` verbatim (fenced JSON intact).").split("\n\n---\n")[0]
    + "\n\n---\nDone means: `docs/spike.md` merged; no code, tests or plugin.yaml needed for this issue.")
# state: corrupt -> shadow (breaker comes later)
edit(2, lambda b: b.replace("and a \"\n  \"breaker trip", "").replace(
    "and a breaker trip (never read as empty)",
    "and fall back to `shadow` until resumed (never read as empty; the breaker issue #29 "
    "later records it as a trip)"))
# CI: doctor too, hermes binary
edit(1, lambda b: b.replace("GitHub Actions (tests + `plugins validate`)",
    "GitHub Actions (tests, plus `hermes plugins doctor . --ci` and `hermes plugins validate .` "
    "against hermes-agent installed with `pip install git+https://github.com/NousResearch/hermes-agent@v0.22.5` "
    "and the oldest supported tag v0.21.6)"))
# gate depends on lessons
edit(7, set_deps("#25, #8"))
# restore: memory revert later, no hard dep on wiki-hint#5
edit(26, set_deps("#8, #22"))
edit(26, lambda b: b.replace("memory via the wiki-hint revert contract.",
    "memory restore is a separate later step once seppegadeyne/hermes-wiki-hint#5 is merged; "
    "until then memory lessons are report-only."))
# applier: write-block hook, final-response plan, screening, wiki/memory report-only until ready
edit(27, lambda b: b.replace("`apply-plan.json` schema; every lesson through `guard.py`;",
    "Apply-plan JSON schema (the dream agent's final response, parsed from the newest "
    "unprocessed `cron/output/<dream-job>/*.md`); every lesson screened with `screen.py` and "
    "checked by `guard.py` (incl. the 'next attempt must differ' check against `tried`); wiki "
    "lessons report-only until #12, memory lessons report-only until the wiki-hint contract "
    "(seppegadeyne/hermes-wiki-hint#5);"))
# skill: final response, no files; write-block hook
edit(9, lambda b: b.replace("write at most `max_applies` lessons to the plan path. Read-only tools only.",
    "return at most `max_applies` lessons as one fenced JSON block in the final response (it "
    "writes no files). Also build the `pre_tool_call` hook that blocks every write tool "
    "(write_file, patch, terminal, execute_code, skill_manage, memory, cronjob, send_message, "
    "mcp__*) in dream-job sessions; a block counts as a guard veto. Job uses "
    "`enabled_toolsets: [file, skills]`, `max_turns: 30`."))
edit(9, lambda b: b.replace("Acceptance: skill registered", "Acceptance: hook test (write_file blocked, read_file allowed, only in dream sessions); skill registered"))
# commands depend on install (pause pauses own jobs)
edit(10, set_deps("#26, #19, #11"))
# heal: H-records, shadow, side_effect definition
edit(13, add("Pauses create a heal record `H-<n>` (`paused_reason = \"hermes-dream:H-<n> ...\"`); "
    "the tick resumes its own pause when a lesson for that job reaches `verifying` and triggers "
    "one verification run. In `shadow` heal acts on nothing. `side_effect_tools` is the only "
    "definition of a side effect."))
# report: who sends
edit(20, add("Sending: the tick is a no_agent job; Hermes delivers its stdout to the job's "
    "deliver target. Print the morning report once a day and the weekly report on Mondays; "
    "print nothing otherwise. The plugin never sends messages itself."))
# release needs wiki
edit(17, set_deps("#29, #30, #16, #12"))
