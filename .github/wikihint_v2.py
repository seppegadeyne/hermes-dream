#!/usr/bin/env python3
"""One-off: align the wiki-hint issues with hermes-dream plan v2 (§4.5, §9)."""
import json, subprocess

R = "seppegadeyne/hermes-wiki-hint"
FOOT = ("\n\nContext: https://github.com/seppegadeyne/hermes-dream/blob/main/docs/plan.md §9. "
        "Keep the plugin read-only: audit reports, the upkeep run acts via MAINTENANCE.md and "
        "memory_edit.py. Tests: `python3 test_wiki_hint.py && python3 test_maintenance.py`.")


def gh(*a):
    r = subprocess.run(["gh", *a], capture_output=True, text=True)
    return (r.stdout or r.stderr).strip()


print(gh("issue", "close", "1", "-R", R, "--reason", "completed", "--comment",
         "Covered by 1.6.0 (maintenance.py read-only audit) and 1.7.0 (upkeep cron). "
         "Remaining hermes-dream related work is tracked in the newer issues."))

print(gh("issue", "edit", "2", "-R", R, "--body",
 "Snapshot each memory file per run (entry fingerprints + short preview, no text for entries that "
 "hit the secret screen) in a state file under `$HERMES_HOME/plugin-data/wiki-hint/` (first "
 "persistent state of this plugin; atomic write). When a large share of entries or chars "
 "disappears between runs, or a long entry loses half of itself, report it in `--attention` with "
 "the lost entries named. Reworded, merged or split entries are not a loss. Changes made through "
 "the memory-edit contract with a caller tag (e.g. a hermes-dream lesson id) are expected and "
 "not reported.\n\nAcceptance: tests for real loss vs reword/merge/split vs tagged change." + FOOT))

print(gh("issue", "edit", "3", "-R", R, "--body",
 "List a few old memory entries per run as questions (\"still true?\") in the upkeep report that "
 "reaches the operator's channel. Answers come back through a small command "
 "(`/wiki-audit keep <n>` / `/wiki-audit drop <n>`, or the CLI); unanswered questions return "
 "after a short cooldown, kept/rewritten entries rest 90 days. State under "
 "`$HERMES_HOME/plugin-data/wiki-hint/`. Nothing is removed without an answer.\n\nAcceptance: "
 "state with cooldowns, command tests, MAINTENANCE.md section." + FOOT))

contract = gh("issue", "create", "-R", R, "--title",
 "memory_edit: stable contract for other plugins (CLI, JSON schema, entry-level revert)",
 "--body",
 "hermes-dream applies memory lessons through wiki-hint instead of writing MEMORY.md itself.\n\n"
 "- CLI entry point `hermes wiki-hint memory-edit apply|revert|show --json` (callers find it via "
 "the CLI, not a file path), same lock and backups as `memory_edit.py`.\n"
 "- Documented apply-plan JSON schema with a `contract_version`, a `caller` tag (e.g. "
 "`hermes-dream:L-17`) and stable exit codes.\n"
 "- `revert <change-id>`: removes only the entries that change added and restores only the "
 "entries it replaced, when they are still unchanged; otherwise reports `conflict`. Never a "
 "whole-file restore.\n- `--check` output includes the contract version.\n\nAcceptance: schema "
 "doc, tests for apply/revert/conflict, old `memory_edit.py` usage keeps working." + FOOT)
lock = gh("issue", "create", "-R", R, "--title",
 "Shared vault lock for upkeep and other writers",
 "--body",
 "The upkeep run and hermes-dream both write the vault. Add one advisory lock "
 "(`flock` on `<vault>/.wiki-lock` or under plugin-data, documented) taken by the upkeep for "
 "its whole repair pass and exposed for other plugins (`hermes wiki-hint lock --json` or a "
 "documented path + protocol). A writer that cannot get it within N seconds skips and retries "
 "next run.\n\nAcceptance: two concurrent writers never interleave; documented in "
 "MAINTENANCE.md." + FOOT)
print(contract, lock)
json.dump({"wh-contract": int(contract.rsplit("/", 1)[-1]), "wh-lock": int(lock.rsplit("/", 1)[-1])},
          open(__file__.replace("wikihint_v2.py", "wikihint_numbers.json"), "w"))
