from __future__ import annotations

import json
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
            "--no-build-isolation",
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
        # Skip global site-packages: this clean-room check should discover only
        # the installed tutorial wheel, not scan unrelated developer packages.
        [sys.executable, "-S", "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env={
            "PATH": str(Path(sys.executable).parent),
            "PYTHONPATH": os.pathsep.join((str(target), str(root / "python"))),
        },
    )

    assert "com.example.ronin.tutorial" in result.stdout


def test_first_party_plugins_discover_from_clean_main_wheel(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
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
            str(root),
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheelhouse),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(wheelhouse.glob("ronin_studio-*.whl"))
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
        "import json; from studio_runtime import discover_plugins; "
        "print(json.dumps(sorted(r.manifest.id for r in "
        "discover_plugins(ignore_load_errors=True))))"
    )
    clean_env = os.environ.copy()
    clean_env.update(
        {
            "PATH": str(Path(sys.executable).parent),
            "PYTHONPATH": str(target),
            "PYTHONNOUSERSITE": "1",
        }
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-S", "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env=clean_env,
    )

    assert json.loads(result.stdout) == [
        "com.ronin.synthetic-data-studio",
        "com.sauronshepherd.ronin.cloud-studio",
        "com.sauronshepherd.ronin.data-enginerring-studio",
        "com.sauronshepherd.ronin.logging",
        "com.sauronshepherd.ronin.ml-studio",
        "com.sauronshepherd.ronin.monitoring",
        "com.sauronshepherd.ronin.workspaces",
    ]
