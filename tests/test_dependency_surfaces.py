from __future__ import annotations

from pathlib import Path

import pytest

from tools.dependency_surfaces import (
    DependencySurfaceError,
    _exact_requirements,
    dependency_surfaces,
    qualification_tool_requirements,
)


def test_qualification_manifest_accepts_hash_continuations() -> None:
    root = Path.cwd()
    requirements = qualification_tool_requirements(root)
    source_requirements = [
        line.strip()
        for line in (root / "third_party/qualification-tools-v1.in")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert _exact_requirements(source_requirements, surface="qualification-tools-v1.in") == (
        requirements
    )
    assert {
        "build": "1.6.0",
        "pip-audit": "2.10.1",
        "packaging": "26.3",
        "pyproject-hooks": "1.2.0",
        "pytest": "8.4.2",
    }.items() <= requirements.items()
    assert {
        "cachecontrol",
        "cyclonedx-python-lib",
        "requests",
        "tomli",
    } <= set(requirements)


def test_exact_requirements_rejects_ambiguous_surfaces() -> None:
    with pytest.raises(DependencySurfaceError, match="conflicting versions"):
        _exact_requirements(["demo==1.0", "demo==2.0"], surface="test")


def test_dependency_surface_is_versioned_and_split() -> None:
    payload = dependency_surfaces(Path.cwd())
    assert payload["schema_version"] == 1
    assert payload["qualification_tools"]["build"] == "1.6.0"
