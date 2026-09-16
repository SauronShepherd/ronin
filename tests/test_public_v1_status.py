"""Regression tests for the Public v1 status-ledger contract."""

from __future__ import annotations

import importlib.util
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
