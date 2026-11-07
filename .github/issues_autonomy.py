#!/usr/bin/env python3
"""One-off: switch the issue plan from human approval to autonomous with guardrails (plan §2, §4.5, §4.6, §4.8)."""
import subprocess

R = "seppegadeyne/hermes-dream"
COMMON = ("\n\n---\nRead first: `AGENTS.md`, `docs/plan.md` (sections named above). "
          "Done means: tests green (`python3 -m unittest discover -s tests`), "
          "`hermes plugins doctor . --ci` and `hermes plugins validate .` green, plan updated "
          "if a decision changed, PR links this issue.")


def gh(*a):
    r = subprocess.run(["gh", *a], capture_output=True, text=True)
    print((r.stdout or r.stderr).strip())


EDITS = {
 8: ("Lessons: numbering, lifecycle state, before-states",
     "Plan: §3 items 4-6, §4.4, §4.8.\n\n"
     "- Immutable numbers `L-<n>`, keyed by signature fingerprint.\n"
     "- Lifecycle: detected -> applied -> verifying -> kept | rolled back | escalated; "
     "`tried` list per signature so a second attempt must differ.\n"
     "- Before-state record per change (skill ledger entry id, old cron job fields, wiki file "
     "sha256 + content, memory backup path).\n- Caps: `max_applies` per night, one open change "
     "per target.\n\nAcceptance: state-machine tests for every transition."),
 9: ("Dream skill: hermes-dream:dream (decide and apply)",
     "Plan: §4.4, §4.5, §4.8.\n\n"
     "`skills/dream/SKILL.md` for the nightly turn: read payload, check the target for an "
     "existing lesson, skip denylisted targets (report only), pick at most `max_applies` "
     "lessons, apply each through its path (skill_manage patch, memory_edit.py when wiki-hint "
     "is installed, llm-wiki procedure, cron edit / resume), record the before-state, write "
     "the morning report with `/dream undo L-n` per change. No flagged shell commands "
     "(cron_mode).\n\nAcceptance: skill registered as `hermes-dream:dream`; dry run on a "
     "fixture payload in `mode: shadow` and one real apply in a test home."),
 10: ("/dream overrides: show, undo, block, pause, resume",
      "Plan: §4.5.\n\n"
      "- `ctx.register_command(\"dream\", ...)` with args hint and text argument mode; same "
      "actions on the CLI.\n- `undo L-n` restores the before-state (shared code with the "
      "automatic rollback), `block L-n <reason>` = undo + never retry the signature, "
      "`pause`/`resume` = kill switch for both jobs.\n- No agent needed, no "
      "`allow_gateway_injection`.\n\nAcceptance: handler tests with fake ctx per action; manual "
      "test on one messaging platform."),
 13: ("Heal job: transient retry, pause after repeated failures",
      "Plan: §4.6.\n\n"
      "- `no_agent` cron job every 15 min, reads `executions.db` + journal, no model.\n"
      "- Transient (429/5xx/timeout) after >=1 API call: one re-run via `trigger_job` after "
      "`retry_delay_minutes`, max `max_retries_per_day`.\n"
      "- Never re-run when the failed session already made a successful call to a "
      "`side_effect_tools` tool, or the job is in `retry_exclude`.\n"
      "- `pause_after_failures` identical consecutive failures: pause with a plugin "
      "`paused_reason`; the nightly run resumes after a fix.\n\nAcceptance: tests incl. never "
      "retry with `api_call_count == 0`, never after a side effect, never twice a day, pause and "
      "resume path."),
 17: ("Release 0.1.0 and first live week",
      "Plan: §10.\n\nShip `mode: shadow` until the verification + rollback + circuit-breaker "
      "issues are merged; then default `autonomous`. Install on one Hermes, run one live week, "
      "and record in the CHANGELOG: lessons applied / kept / rolled back / escalated, heal "
      "actions, and failed cron runs per week before vs after.\n\nAcceptance: live-week numbers "
      "in this issue; thresholds tuned with evidence."),
}

for n, (t, b) in EDITS.items():
    gh("issue", "edit", str(n), "-R", R, "--title", t, "--body", b + COMMON)

NEW = [
 ("M5 Self-heal + verify", "Verification and automatic rollback",
  "Plan: §4.8 items 1-4.\n\n"
  "- After apply, watch the triggering signature for `verify_days` (skills/wiki/memory) or "
  "`verify_runs` runs (cron).\n- Kept when it drops (zero for job failures) and no new "
  "signature appears in the same target; otherwise restore the before-state, add the change "
  "to `tried`, allow one different fix, then escalate after `max_attempts`.\n- Rollback per "
  "target: `hermes curator rollback <ledger-id>` for skills, saved job fields for cron, file "
  "content for wiki, memory backup via memory_edit.py.\n\nAcceptance: golden tests (b) and "
  "(a) from plan §8b; rollback restores byte-identical before-state."),
 ("M3 Dream + apply", "Guardrails: denylist, caps, circuit breaker, kill switch",
  "Plan: §4.8 items 5-8.\n\n"
  "- Hard-coded denylist (`SOUL.md`, `config.yaml`, `.env`, secrets paths, `USER.md`, plugin "
  "and Hermes code, other repos, deletions of skills/pages/jobs, sending messages); one "
  "shared check used by every apply path, not configurable away.\n- Caps per night and per "
  "target.\n- Circuit breaker: more than `breaker_rollbacks` rollbacks in 7 days -> detect + "
  "report only until `hermes dream resume`.\n- `mode`: autonomous | shadow | off.\n\n"
  "Acceptance: golden tests (d) and (e); a denylisted target in a fixture payload is never "
  "written."),
 ("M5 Self-heal + verify", "Morning report with undo per change",
  "Plan: §4.8 item 9, §4.7.\n\nAfter each nightly run and heal action batch: what changed, "
  "what was verified, kept or rolled back, what was escalated, each with `/dream undo L-n`. "
  "Delivered through the job's deliver target; nothing on quiet nights.\n\nAcceptance: "
  "report rendered from fixture state in en and nl."),
]
MS = {"M3 Dream + review": "M3 Dream + review", "M5 Recover + measure": "M5 Recover + measure"}
for ms, t, b in NEW:
    gh("issue", "create", "-R", R, "--title", t, "--body", b + COMMON, "--label", "plan",
       "--milestone", ms)
