#!/usr/bin/env python3
"""Check that Ronin exposes the data-engineering CLI surface."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

TOP = {"doctor", "validate", "plan", "submit", "status", "logs", "evidence", "connectors"}
SUB = {"capabilities", "discover", "preview", "plan", "checkpoint-health"}


def resolve_executable(value: str) -> str | None:
    """Resolve a Ronin command from PATH or an explicit executable path."""
    resolved = shutil.which(value)
    if resolved is not None:
        return resolved

    candidate = Path(value).expanduser()
    if candidate.is_file():
        return str(candidate.resolve())
    return None


def _run_help(executable: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - the user-selected Ronin executable is the target
        [executable, *arguments],
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )


def _help_text(result: subprocess.CompletedProcess[str]) -> str:
    return f"{result.stdout or ''}\n{result.stderr or ''}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ronin", default="ronin")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    executable = resolve_executable(args.ronin)
    if executable is None:
        error_result = {"ok": False, "error": "ronin_not_found"}
        print(json.dumps(error_result, sort_keys=True) if args.json else "Ronin CLI not found")
        return 2

    try:
        root = _run_help(executable, "--help")
        connectors = _run_help(executable, "connectors", "--help")
    except (OSError, subprocess.TimeoutExpired) as error:
        error_result = {"ok": False, "error": "ronin_check_failed", "detail": str(error)}
        print(
            json.dumps(error_result, sort_keys=True)
            if args.json
            else f"Ronin CLI check failed: {error}"
        )
        return 2

    missing_top = sorted(command for command in TOP if command not in _help_text(root))
    missing_connectors = sorted(command for command in SUB if command not in _help_text(connectors))
    result: dict[str, Any] = {
        "ok": root.returncode == 0
        and connectors.returncode == 0
        and not missing_top
        and not missing_connectors,
        "missing_top": missing_top,
        "missing_connectors": missing_connectors,
    }
    print(json.dumps(result, sort_keys=True) if args.json else result)
    return 0 if result["ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
