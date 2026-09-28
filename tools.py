"""Tool handlers: shell out to the local `smcub` CLI and return JSON strings.

Design rules enforced here:
- arguments are passed as a list, never through a shell, so a path can never
  be interpreted as a command;
- every handler returns a JSON string and never raises;
- no handler places or cancels an order, opens a broker connection, fetches
  the network, or produces financial advice. The subprocess is the local
  read-only harness and its output is passed through unchanged.
- path-sensitive tools fail closed unless run_root is configured. Every input
  and output path is checked after filesystem resolution so symlinks and parent
  traversal cannot escape that root.
"""

from __future__ import annotations

import json
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


def _resolve_root(ctx_config: dict[str, Any]) -> tuple[Path | None, str | None]:
    """Resolve the configured root, refusing an absent or non-directory root."""
    raw = str(ctx_config.get("run_root") or "").strip()
    if not raw:
        return None, "run_root must be configured for this path-sensitive tool"
    try:
        root = Path(raw).expanduser().resolve(strict=True)
    except OSError as exc:
        return None, f"run_root cannot be resolved: {exc}"
    if not root.is_dir():
        return None, f"run_root is not a directory: {root}"
    return root, None


def _relative_to_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _resolve_existing_under_root(
    ctx_config: dict[str, Any], path: Path, *, kind: str
) -> tuple[Path | None, str | None]:
    """Validate an existing file or directory, including symlink containment."""
    root, failure = _resolve_root(ctx_config)
    if failure:
        return None, failure
    assert root is not None
    try:
        resolved = path.expanduser().resolve(strict=True)
    except FileNotFoundError:
        return None, f"path does not exist: {path}"
    except OSError as exc:
        return None, f"could not resolve path: {exc}"
    if not _relative_to_root(resolved, root):
        return None, f"path is outside the configured run_root: {path}"
    if kind == "directory" and not resolved.is_dir():
        return None, f"path is not a directory: {path}"
    if kind == "file" and not resolved.is_file():
        return None, f"path is not a file: {path}"
    return resolved, None


def _resolve_output_under_root(
    ctx_config: dict[str, Any], path: Path
) -> tuple[Path | None, str | None]:
    """Validate an output directory, allowing a new directory below root."""
    root, failure = _resolve_root(ctx_config)
    if failure:
        return None, failure
    assert root is not None
    candidate = path.expanduser()
    try:
        resolved = candidate.resolve(strict=False)
    except OSError as exc:
        return None, f"could not resolve output directory: {exc}"
    if not _relative_to_root(resolved, root):
        return None, f"output directory is outside the configured run_root: {path}"

    existing = candidate
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    try:
        existing_resolved = existing.resolve(strict=True)
    except OSError as exc:
        return None, f"could not resolve output parent: {exc}"
    if not existing_resolved.is_dir():
        return None, f"output parent is not a directory: {existing}"
    if not _relative_to_root(existing_resolved, root):
        return None, f"output directory is outside the configured run_root: {path}"
    if candidate.exists() and not resolved.is_dir():
        return None, f"output path is not a directory: {path}"
    return resolved, None


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
    return path, None


def smcub_doctor(args: dict[str, Any], **kwargs: Any) -> str:
    ctx_config = kwargs.get("config") or {}
    argv = ["doctor"]
    returncode, stdout, stderr = _run(ctx_config, argv)
    return _payload(returncode, stdout, stderr, argv)


def _path_tool(args, kwargs, key, argv_for, *, kind: str):
    ctx_config = kwargs.get("config") or {}
    path, failure = _require_path(args, key)
    if failure:
        return _error(failure)
    assert path is not None
    checked, failure = _resolve_existing_under_root(ctx_config, path, kind=kind)
    if failure:
        return _error(failure)
    assert checked is not None
    argv = argv_for(str(checked))
    returncode, stdout, stderr = _run(ctx_config, argv)
    return _payload(returncode, stdout, stderr, argv)


def smcub_validate_envelope(args: dict[str, Any], **kwargs: Any) -> str:
    return _path_tool(
        args,
        kwargs,
        "envelope_path",
        lambda p: ["validate-envelope", "--", p],
        kind="file",
    )


def smcub_replay_evidence_pack(args: dict[str, Any], **kwargs: Any) -> str:
    return _path_tool(
        args,
        kwargs,
        "pack_dir",
        lambda p: ["replay-evidence-pack", "--", p],
        kind="directory",
    )


def smcub_inspect_artifacts(args: dict[str, Any], **kwargs: Any) -> str:
    return _path_tool(
        args,
        kwargs,
        "run_dir",
        lambda p: ["inspect-artifacts", "--", p],
        kind="directory",
    )


def smcub_evaluate_run(args: dict[str, Any], **kwargs: Any) -> str:
    horizon = str(args.get("horizon") or "d1").strip()
    if horizon not in {"d1", "d3"}:
        return _error("horizon must be one of: d1, d3")
    return _path_tool(
        args,
        kwargs,
        "run_dir",
        lambda p: ["evaluate-run", "--horizon", horizon, "--", p],
        kind="directory",
    )


def smcub_build_evidence_pack(args: dict[str, Any], **kwargs: Any) -> str:
    ctx_config = kwargs.get("config") or {}
    run_dir, failure = _require_path(args, "run_dir")
    if failure:
        return _error(failure)
    output_raw = str(args.get("output_dir") or "").strip()
    if not output_raw:
        return _error("missing required argument: output_dir")
    rule_raw = str(args.get("rule_candidate") or "").strip()
    if not rule_raw:
        return _error("missing required argument: rule_candidate")
    horizon = str(args.get("horizon") or "d1").strip()
    if horizon not in {"d1", "d3"}:
        return _error("horizon must be one of: d1, d3")

    assert run_dir is not None
    checked_run, failure = _resolve_existing_under_root(
        ctx_config, run_dir, kind="directory"
    )
    if failure:
        return _error(failure)
    rule_candidate = Path(rule_raw).expanduser()
    checked_rule, failure = _resolve_existing_under_root(
        ctx_config, rule_candidate, kind="file"
    )
    if failure:
        return _error(failure)
    assert checked_rule is not None
    if checked_rule.suffix.lower() != ".json":
        return _error("rule_candidate must be a JSON file")
    checked_output, failure = _resolve_output_under_root(
        ctx_config, Path(output_raw)
    )
    if failure:
        return _error(failure)
    assert checked_run is not None and checked_output is not None
    argv = [
        "build-evidence-pack",
        f"--sample={checked_run}",
        f"--rule-candidate={checked_rule}",
        f"--horizon={horizon}",
        "--",
        str(checked_output),
    ]
    returncode, stdout, stderr = _run(ctx_config, argv)
    return _payload(returncode, stdout, stderr, argv)
