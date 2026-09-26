# hermes-smartmoney-cub

A [Hermes Agent](https://github.com/NousResearch/hermes-agent) plugin that exposes
[SmartMoney-Cub](https://github.com/myc0576/SmartMoney-Cub) as six review tools.

```text
READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE
```

SmartMoney-Cub is a read-only trading journal and review harness. It records
decisions, imports your own executions, computes analytics, and evolves rules
through challenger to champion governance. This plugin does not reimplement any of
that. It wraps the local `smcub` CLI so an agent can drive the review loop and
present evidence to a human.

## What it does not do

- It never places or cancels an order.
- It never connects to a broker or modifies an account.
- It never fetches market data on its own.
- It never returns financial advice, a price target, a position size, or a signal.
- It does not run arbitrary commands for you; capture-run stays yours to invoke.

An `ALERT`, `WATCH`, `AVOID`, or a `grade` value is recorded review context. It is
not an instruction to trade, and neither this plugin nor the harness will treat it
as one.

## Tools

| Tool | Purpose |
| --- | --- |
| `smcub_doctor` | Report harness health, version, and the safety declaration. |
| `smcub_validate_envelope` | Validate a `run_envelope.json` against the schema. |
| `smcub_build_evidence_pack` | Freeze a run plus delayed outcome into a hashed pack. |
| `smcub_replay_evidence_pack` | Recompute a pack and compare against its hashes. |
| `smcub_evaluate_run` | Grade one run directory against its recorded outcome. |
| `smcub_inspect_artifacts` | Report promotion readiness and the honest sample count. |

A bundled skill, `smartmoney-review`, walks the agent through the full loop and
enforces the reporting rules. Load it with `skill_view("smartmoney-cub:smartmoney-review")`.

## Requirements

- Hermes Agent 0.19 or newer.
- The harness CLI on your `PATH`:

  ```bash
  git clone https://github.com/myc0576/SmartMoney-Cub.git
  cd SmartMoney-Cub
  python -m pip install -e ".[dev]"
  smcub doctor
  ```

  The harness is not published on PyPI; install it from source or from the wheel
  attached to its GitHub Releases. Set `smcub_command` in the plugin settings if
  the executable lives somewhere else.

## Install

```bash
hermes plugins install myc0576/hermes-smartmoney-cub --enable
hermes plugins list
```

Or copy the directory into `~/.hermes/plugins/smartmoney-cub/`.

## Settings

| Key | Default | Meaning |
| --- | --- | --- |
| `smcub_command` | `smcub` | Command used to invoke the harness. |
| `timeout_seconds` | `120` | Per-invocation timeout. |
| `run_root` | empty | Optional directory that run and pack paths must live under. Empty means the plugin only warns when a path escapes. |

## Safety notes

Handlers pass arguments to the CLI as a list with `shell=False`, so a path can
never be interpreted as a command. Every handler returns a JSON string and never
raises; a missing path, a missing CLI, and a timeout all come back as explicit
errors rather than a silent empty success.

`build-evidence-pack` and `evaluate-run` write inside the run directory you name,
which is what the harness already does. Nothing is written outside it. The plugin
makes no network calls of its own.

## Development

```bash
python3 -m pytest tests/ -q          # 11 tests, stub CLI, no network
python3 scripts/check_surface.py     # declared vs registered tools, 6/6
```

`tests/` uses a stub `smcub` so it proves the contract without the real harness
installed. `scripts/check_surface.py` imports the plugin, calls `register()` against
a recording context, and asserts that `plugin.yaml` matches what actually
registered.

## License

MIT. See [LICENSE](LICENSE).
