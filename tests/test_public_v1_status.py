"""Regression tests for the Public v1 status-ledger contract."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _status_tool():
    path = Path(__file__).parents[1] / "tools" / "generate_public_v1_status.py"
    spec = importlib.util.spec_from_file_location("public_v1_status_tool", path)
    if spec is None or spec.loader is None:
        raise AssertionError("status tool could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_v1_ledgers_share_observed_sha() -> None:
    tool = _status_tool()
    machine_sha, markdown_sha = tool._read_observed()

    assert machine_sha == markdown_sha
    assert len(machine_sha) == 40
    assert all(character in "0123456789abcdef" for character in machine_sha)


def test_status_check_is_fail_closed_for_divergence() -> None:
    tool = _status_tool()
    tool.check()


def test_pull_request_status_check_uses_base_sha_not_synthetic_merge_head(
    monkeypatch, tmp_path
) -> None:
    tool = _status_tool()
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps({"pull_request": {"base": {"sha": "a" * 40}}}), encoding="utf-8"
    )
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setattr(tool, "_read_observed", lambda: ("a" * 40, "a" * 40))
    observed: list[list[str]] = []

    def run(args, **_kwargs):
        observed.append(args)

        class Result:
            returncode = 0
            stdout = "0\n"

        return Result()

    monkeypatch.setattr(tool.subprocess, "run", run)
    tool.check()

    assert ["git", "rev-list", "--count", "--no-merges", f"{'a' * 40}..{'a' * 40}"] in observed
