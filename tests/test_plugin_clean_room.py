from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_third_party_tutorial_builds_and_discovers_from_wheel(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    source = root / "examples" / "ronin-plugin-tutorial"
    wheelhouse = tmp_path / "wheelhouse"
    target = tmp_path / "target"
    wheelhouse.mkdir()
    target.mkdir()

    subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            str(source),
            "--no-deps",
            "--wheel-dir",
            str(wheelhouse),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(wheelhouse.glob("ronin_plugin_tutorial-*.whl"))
    subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            str(wheel),
            "--no-deps",
            "--target",
            str(target),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    script = (
        "from studio_runtime import discover_plugins; "
        "records=discover_plugins(ignore_load_errors=True); "
        "print([r.manifest.id for r in records if r.manifest.id == "
        "'com.example.ronin.tutorial'])"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env={
            "PATH": str(Path(sys.executable).parent),
            "PYTHONPATH": os.pathsep.join((str(target), str(root / "python"))),
        },
    )

    assert "com.example.ronin.tutorial" in result.stdout
