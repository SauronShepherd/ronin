"""Build-independent audit for a Cloud Studio wheel."""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path


def main(wheel: str) -> None:
    names = zipfile.ZipFile(wheel).namelist()
    required_suffixes = (
        "studio_cloud/plugin.py",
        "cloud-studio.html",
        "cloud-studio.css",
        "cloud-studio.js",
        "entry_points.txt",
    )
    missing = [
        suffix for suffix in required_suffixes if not any(name.endswith(suffix) for name in names)
    ]
    if missing:
        raise SystemExit(f"wheel is missing Cloud Studio artifacts: {missing}")
    print(f"Cloud Studio wheel audit passed: {Path(wheel).name}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python tools/cloud_studio_wheel_audit.py PATH_TO_WHEEL")
    main(sys.argv[1])
