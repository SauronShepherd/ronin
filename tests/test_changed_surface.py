from __future__ import annotations

import pytest

from tools.changed_surface import build_manifest, classify


def test_changed_surface_classifies_known_domains() -> None:
    assert classify("web/js/app.js") == "ui"
    assert classify("python/studio_migration/profiles.py") == "migration"
    assert classify(".github/workflows/ci.yml") == "qualification"
    assert classify("docs/product/PUBLIC_V1_SCOPE.md") == "documentation"


def test_changed_surface_fails_closed_for_ambiguous_or_unknown_paths() -> None:
    assert classify("python/studio_ml/plugin.py") == "ml"
    with pytest.raises(ValueError, match="unclassified"):
        build_manifest(["unknown/file.bin"], base="base", head="head")


def test_changed_surface_classifies_current_candidate_without_unassigned_paths() -> None:
    from tools.changed_surface import changed_files

    paths = changed_files("origin/main", "HEAD")
    manifest = build_manifest(paths, base="origin/main", head="HEAD")
    assert manifest["files"] == len(paths)
    assert manifest["subsystems"]
