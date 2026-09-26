---
name: smartmoney-review
description: Guide an agent through a read-only SmartMoney-Cub review - capture a run, validate the envelope, build and replay an evidence pack, and present the result to a human without turning it into a trading instruction.
---

# SmartMoney-Cub review workflow

Use this when the user asks to review a trade, journal a decision, or build a
reproducible record of a review run.

## The one rule

Every status this workflow produces is a **review** status. ALERT, WATCH,
AVOID, and any grade are descriptions of recorded context. None of them is an
instruction to buy or sell. Never convert one into an order, a size, or a
recommendation, and never tell the user what to trade.

## Steps

1. **Check the harness.** Call smcub_doctor. If the CLI is missing, tell the
   user to install smartmoney-cub-harness rather than substituting your own
   numbers.
2. **Capture a run.** Ask the user to run `smcub capture-run <offline-command>`
   themselves with their own --agent-name. The plugin does not run arbitrary
   commands on their behalf.
3. **Validate.** Call smcub_validate_envelope on the produced
   run_envelope.json. Stop and surface the error if validation fails.
4. **Build the pack.** Once delayed D1/D3 outcome data exists, call
   smcub_build_evidence_pack.
5. **Replay.** Call smcub_replay_evidence_pack. Only a verified report means
   the pack is intact. A pending_review or blocked report is a stop sign.
6. **Inspect before presenting.** Call smcub_inspect_artifacts and report the
   sample count honestly. Never present a performance number without it.

## Reporting

Always state the sample size next to any performance figure, name the horizon
(d1/d3), and say plainly that a small self-selected sample is not a
controlled study. If a promotion threshold is not met, say so instead of
softening it.

Preserve this declaration on anything you output:

```text
READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE
```
