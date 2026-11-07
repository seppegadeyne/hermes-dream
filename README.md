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
- **Dream**: one agent turn turns the clusters into a few numbered lessons (a skill pitfall, a
  cron prompt fix, a wiki page, a memory entry) and applies them through Hermes' own paths.
- **Verify**: over the next days or runs, a lesson must make its failure stop. If it does not,
  or something new breaks, it is rolled back automatically and a different fix is tried once;
  then it is escalated to you.
- **Heal**: every 15 minutes, without a model, failed cron jobs get one re-run after a transient
  error (never when the run already sent or changed something) and are paused after repeated
  identical failures.
- **Report**: every morning (what changed, with `/dream undo L-n`) and weekly (did the setup
  get better?).

It runs on its own. Guardrails instead of approvals: every change is reversible, verified and
rolled back when it does not help; a hard denylist (config, `.env`, `SOUL.md`, `USER.md`,
plugin code, deletions, sending messages); caps per night; a circuit breaker after repeated
rollbacks; `hermes dream pause` as kill switch. `mode: shadow` makes it propose only.

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
