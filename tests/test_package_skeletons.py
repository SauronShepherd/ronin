from __future__ import annotations

import importlib

import pytest

PACKAGES = (
    "studio_core",
    "studio_notebook",
    "studio_kernel",
    "studio_runners",
    "studio_orchestrator",
    "studio_storage",
    "studio_vcs",
    "studio_server",
    "studio_cli",
)


@pytest.mark.parametrize("name", PACKAGES)
def test_package_imports_and_declares_all(name: str) -> None:
    module = importlib.import_module(name)
    assert isinstance(module.__all__, tuple)
    assert module.__doc__
