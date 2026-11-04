#!/usr/bin/env python3
"""Check that the installed Ronin CLI exposes the core skill commands."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

REQUIRED = {
    "doctor",
    "validate",
    "plan",
    "submit",
    "status",
    "logs",
    "evidence",
    "jobs",
    "cancel",
}


def resolve_executable(value: str) -> str | None:
    """Resolve a Ronin command from PATH or an explicit executable path."""
    resolved = shutil.which(value)
    if resolved is not None:
        return resolved

    candidate = Path(value).expanduser()
    if candidate.is_file():
        return str(candidate.resolve())
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ronin", default="ronin")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    executable = resolve_executable(args.ronin)
    if executable is None:
        result = {"ok": False, "error": "ronin_not_found", "missing": sorted(REQUIRED)}
        print(json.dumps(result, sort_keys=True) if args.json else "Ronin CLI not found")
        return 2

    try:
        completed = subprocess.run(  # noqa: S603 - the user-selected Ronin executable is the target
            [executable, "--help"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        result = {"ok": False, "error": "ronin_check_failed", "detail": str(error)}
        print(
            json.dumps(result, sort_keys=True) if args.json else f"Ronin CLI check failed: {error}"
        )
        return 2

    help_text = f"{completed.stdout or ''}\n{completed.stderr or ''}"
    present = sorted(command for command in REQUIRED if command in help_text)
    missing = sorted(REQUIRED - set(present))
    result = {
        "ok": completed.returncode == 0 and not missing,
        "executable": executable,
        "present": present,
        "missing": missing,
    }
    print(
        json.dumps(result, sort_keys=True) if args.json else f"present={present} missing={missing}"
    )
    return 0 if result["ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
