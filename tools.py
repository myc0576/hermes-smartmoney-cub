"""Tool handlers: shell out to the local `smcub` CLI and return JSON strings.

Design rules enforced here:
- arguments are passed as a list, never through a shell, so a path can never
  be interpreted as a command;
- every handler returns a JSON string and never raises;
- no handler places or cancels an order, opens a broker connection, fetches
  the network, or produces financial advice. The subprocess is the local
  read-only harness and its output is passed through unchanged.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

SAFETY = "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"

DEFAULT_TIMEOUT = 120


def _error(message: str, **extra: Any) -> str:
    payload: dict[str, Any] = {"status": "error", "error": message, "safety": SAFETY}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)


def _resolve_command(ctx_config: dict[str, Any]) -> str:
    configured = str(ctx_config.get("smcub_command") or "smcub").strip() or "smcub"
    resolved = shutil.which(configured)
    return resolved or configured


def _timeout(ctx_config: dict[str, Any]) -> int:
    try:
        value = int(ctx_config.get("timeout_seconds") or DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        value = DEFAULT_TIMEOUT
    return max(5, min(value, 3600))


def _containment_warning(ctx_config: dict[str, Any], path: Path) -> str | None:
    root = str(ctx_config.get("run_root") or "").strip()
    if not root:
        return None
    try:
        resolved_root = Path(root).expanduser().resolve()
        resolved_path = path.expanduser().resolve()
        resolved_path.relative_to(resolved_root)
    except ValueError:
        return f"path is outside the configured run_root {resolved_root}"
    except OSError as exc:
        return f"could not resolve path against run_root: {exc}"
    return None


def _run(ctx_config: dict[str, Any], argv: list[str]) -> tuple[int, str, str]:
    command = [ _resolve_command(ctx_config), *argv ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=_timeout(ctx_config),
            shell=False,
            check=False,
        )
        return completed.returncode, completed.stdout or "", completed.stderr or ""
    except FileNotFoundError:
        return 127, "", f"smcub CLI not found: {_resolve_command(ctx_config)}"
    except subprocess.TimeoutExpired:
        return 124, "", f"smcub timed out after {_timeout(ctx_config)}s"
    except OSError as exc:
        return 126, "", f"could not start smcub: {exc}"


def _payload(returncode: int, stdout: str, stderr: str, command: list[str]) -> str:
    parsed: Any = None
    text_out = stdout.strip()
    if text_out:
        try:
            parsed = json.loads(text_out)
        except json.JSONDecodeError:
            parsed = None
    result: dict[str, Any] = {
        "status": "ok" if returncode == 0 else "failed",
        "returncode": returncode,
        "command": " ".join(command),
        "safety": SAFETY,
    }
    if parsed is not None:
        result["result"] = parsed
    elif text_out:
        result["stdout"] = text_out
    if stderr.strip():
        result["stderr"] = stderr.strip()[:4000]
    return json.dumps(result, ensure_ascii=False)


def _require_path(args: dict[str, Any], key: str) -> tuple[Path | None, str | None]:
    raw = str(args.get(key) or "").strip()
    if not raw:
        return None, f"missing required argument: {key}"
    path = Path(raw).expanduser()
    if not path.exists():
        return None, f"path does not exist: {path}"
    return path, None


def _guard(ctx_config: dict[str, Any], path: Path) -> str | None:
    warning = _containment_warning(ctx_config, path)
    return warning


def smcub_doctor(args: dict[str, Any], **kwargs: Any) -> str:
    ctx_config = kwargs.get("config") or {}
    argv = ["doctor"]
    returncode, stdout, stderr = _run(ctx_config, argv)
    return _payload(returncode, stdout, stderr, argv)


def _path_tool(args, kwargs, key, argv_for):
    ctx_config = kwargs.get("config") or {}
    path, failure = _require_path(args, key)
    if failure:
        return _error(failure)
    warning = _guard(ctx_config, path)
    argv = argv_for(str(path))
    returncode, stdout, stderr = _run(ctx_config, argv)
    payload = _payload(returncode, stdout, stderr, argv)
    if warning:
        data = json.loads(payload)
        data["containment_warning"] = warning
        payload = json.dumps(data, ensure_ascii=False)
    return payload


def smcub_validate_envelope(args: dict[str, Any], **kwargs: Any) -> str:
    return _path_tool(args, kwargs, "envelope_path", lambda p: ["validate-envelope", p])


def smcub_replay_evidence_pack(args: dict[str, Any], **kwargs: Any) -> str:
    return _path_tool(args, kwargs, "pack_dir", lambda p: ["replay-evidence-pack", p])


def smcub_inspect_artifacts(args: dict[str, Any], **kwargs: Any) -> str:
    return _path_tool(args, kwargs, "run_dir", lambda p: ["inspect-artifacts", p])


def smcub_evaluate_run(args: dict[str, Any], **kwargs: Any) -> str:
    horizon = str(args.get("horizon") or "d1").strip() or "d1"
    return _path_tool(
        args,
        kwargs,
        "run_dir",
        lambda p: ["evaluate-run", p, "--horizon", horizon],
    )


def smcub_build_evidence_pack(args: dict[str, Any], **kwargs: Any) -> str:
    output_dir = str(args.get("output_dir") or "").strip()

    def argv_for(path: str) -> list[str]:
        argv = ["build-evidence-pack", path]
        if output_dir:
            argv.extend(["--output-dir", output_dir])
        return argv

    return _path_tool(args, kwargs, "run_dir", argv_for)
