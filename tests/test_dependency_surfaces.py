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
    requirements = qualification_tool_requirements(Path.cwd())
    assert requirements >= {
        "build": "1.6.0",
        "pip-audit": "2.10.1",
        "packaging": "26.3",
        "pyproject-hooks": "1.2.0",
        "pytest": "8.4.2",
    }
    assert {
        "CacheControl",
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
