"""Run mutation testing through a temporary source-root alias required by mutmut."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

_SOURCE_ALIAS = Path("src")
_SOURCE_TARGET = Path("python")


def run_mutation() -> None:
    if _SOURCE_ALIAS.exists() or _SOURCE_ALIAS.is_symlink():
        raise RuntimeError("temporary mutation source alias already exists")
    if not _SOURCE_TARGET.is_dir():
        raise RuntimeError("python source root is missing")
    executable = shutil.which("mutmut")
    if executable is None:
        raise RuntimeError("mutmut executable is missing")

    _SOURCE_ALIAS.symlink_to(_SOURCE_TARGET, target_is_directory=True)
    try:
        subprocess.run([executable, "run"], check=True)
        subprocess.run([executable, "export-cicd-stats"], check=True)
    finally:
        _SOURCE_ALIAS.unlink(missing_ok=True)


def main() -> None:
    run_mutation()


if __name__ == "__main__":
    main()
