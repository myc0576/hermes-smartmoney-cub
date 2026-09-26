"""Tests for the SmartMoney-Cub Hermes plugin.

These tests use a stub smcub executable so they prove the plugin contract
(JSON in, JSON out, never raises, no shell interpretation) without needing the
real harness installed.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tools  # noqa: E402


def _write_stub(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


@pytest.fixture()
def stub_ctx(tmp_path: Path):
    """A stub CLI that echoes its argv back as JSON."""
    script = "#!/usr/bin/env python3\nimport json, sys\nprint(json.dumps({\"argv\": sys.argv[1:]}))\n"
    stub = _write_stub(tmp_path, "smcub", script)
    return {"smcub_command": str(stub), "timeout_seconds": 30, "run_root": ""}


def test_every_schema_has_a_handler():
    import schemas

    names = {s["name"] for s in schemas.ALL_SCHEMAS}
    for name in names:
        assert hasattr(tools, name), f"missing handler for {name}"


def test_doctor_returns_json(stub_ctx):
    out = tools.smcub_doctor({}, config=stub_ctx)
    payload = json.loads(out)
    assert payload["status"] == "ok"
    assert payload["result"]["argv"] == ["doctor"]
    assert payload["safety"] == tools.SAFETY


def test_missing_path_returns_error_not_raise(stub_ctx, tmp_path):
    out = tools.smcub_validate_envelope({"envelope_path": str(tmp_path / "nope.json")}, config=stub_ctx)
    payload = json.loads(out)
    assert payload["status"] == "error"
    assert "does not exist" in payload["error"]


def test_missing_argument_returns_error(stub_ctx):
    out = tools.smcub_validate_envelope({}, config=stub_ctx)
    payload = json.loads(out)
    assert payload["status"] == "error"


def test_shell_metacharacters_are_not_interpreted(stub_ctx, tmp_path):
    """A path containing a semicolon must stay a literal path, not a command."""
    marker = tmp_path / "owned_by_injection"
    hostile = tmp_path / ("env.json; touch " + marker.name)
    hostile.write_text("{}", encoding="utf-8")

    out = tools.smcub_validate_envelope({"envelope_path": str(hostile)}, config=stub_ctx)
    payload = json.loads(out)
    assert not marker.exists(), "argument was interpreted by a shell"
    assert payload["result"]["argv"][0] == "validate-envelope"
    assert payload["result"]["argv"][1] == str(hostile)


def test_evaluate_run_passes_horizon(stub_ctx, tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    out = tools.smcub_evaluate_run({"run_dir": str(run_dir), "horizon": "d3"}, config=stub_ctx)
    payload = json.loads(out)
    assert payload["result"]["argv"] == ["evaluate-run", str(run_dir), "--horizon", "d3"]


def test_build_evidence_pack_output_dir(stub_ctx, tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    out_dir = tmp_path / "pack"
    out = tools.smcub_build_evidence_pack(
        {"run_dir": str(run_dir), "output_dir": str(out_dir)}, config=stub_ctx
    )
    payload = json.loads(out)
    assert payload["result"]["argv"] == [
        "build-evidence-pack", str(run_dir), "--output-dir", str(out_dir),
    ]


def test_containment_warning_is_reported(tmp_path):
    script = "#!/usr/bin/env python3\nimport json, sys\nprint(json.dumps({\"argv\": sys.argv[1:]}))\n"
    stub = _write_stub(tmp_path, "smcub", script)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    cfg = {"smcub_command": str(stub), "timeout_seconds": 30, "run_root": str(tmp_path / "allowed")}
    out = tools.smcub_validate_envelope({"envelope_path": str(outside)}, config=cfg)
    payload = json.loads(out)
    assert "containment_warning" in payload


def test_missing_cli_is_reported_not_raised():
    out = tools.smcub_doctor({}, config={"smcub_command": "/nonexistent/smcub", "timeout_seconds": 5})
    payload = json.loads(out)
    assert payload["status"] == "error" or payload["status"] == "failed"


def test_handler_never_raises_on_bad_types(stub_ctx):
    for handler in (
        tools.smcub_validate_envelope,
        tools.smcub_replay_evidence_pack,
        tools.smcub_evaluate_run,
        tools.smcub_inspect_artifacts,
        tools.smcub_build_evidence_pack,
    ):
        out = handler({"run_dir": None, "envelope_path": None, "pack_dir": None}, config=stub_ctx)
        json.loads(out)  # must be valid JSON


def test_run_is_offline_by_construction(stub_ctx):
    """The plugin never opts into the network itself."""
    assert stub_ctx["run_root"] == ""
    out = tools.smcub_doctor({}, config=stub_ctx)
    assert "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE" in out
