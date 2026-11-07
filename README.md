# hermes-dream

Nightly "dreaming" for [Hermes Agent](https://github.com/NousResearch/hermes-agent): turn
yesterday's execution logs into reviewed lessons.

> Status: **planning**. Nothing is built yet. The design lives in [docs/plan.md](docs/plan.md)
> and the work is split into GitHub issues (milestones M1-M6).

## What it will do

```
capture -> collect -> gate -> dream -> review -> apply -> report
```

- **Capture**: cheap observer hooks record failures as they happen (provider errors, tool
  errors, blocked or timed-out approvals, failed subagents), metadata only.
- **Collect**: a nightly script with no LLM groups the last day of cron runs, `errors.log`
  and captured events into recurring signatures.
- **Gate**: on a quiet night the cron job prints `{"wakeAgent": false}` and no model runs.
- **Dream**: one agent turn turns the clusters into a few numbered proposals: a skill
  pitfall, a cron prompt fix, a wiki page, a memory entry, a retry.
- **Review**: you answer `/dream yes L-17` or `/dream no L-18 <reason>`.
- **Apply**: through Hermes' own paths (skill ledger, memory tool, approval queue) and an
  llm-wiki vault.
- **Report**: weekly, including whether applied lessons actually stopped the failure.

It never edits skills, memory, the wiki or cron jobs on its own. The first release runs in
shadow mode: proposals only.

## Why not the built-ins?

Hermes' background review learns from the *current conversation*, the curator *prunes*
skills, and `cron.retry_unreachable` re-runs jobs that never reached the model. None of them
learn from execution across sessions, crons and profiles. hermes-dream fills that gap and
reads their outcomes so it does not repeat them.

## Credits

Several design ideas (deterministic pass before the model, wake gate, corroboration,
every item gets an outcome, caps, screening, robust state) come from
[hermes-dreaming](https://github.com/itpartypattaya/hermes-dreaming) by Anton Vaskov (MIT).
hermes-dream applies them to execution logs instead of conversation facts; no code is copied.

## License

MIT
