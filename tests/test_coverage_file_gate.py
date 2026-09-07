import json
from pathlib import Path

import pytest

from tools.coverage_file_gate import DEFAULT_THRESHOLD, load_coverage, validate_package_files


def _coverage(files: dict[str, float]) -> dict[str, object]:
    return {
        "meta": {"version": "7.16.0"},
        "files": {
            path: {"summary": {"percent_covered": percent}}
            for path, percent in files.items()
        },
    }


def _package(tmp_path: Path, *relative_paths: str) -> Path:
    root = tmp_path / "python" / "studio_storage"
    for relative in relative_paths:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("value = 1\n", encoding="utf-8")
    return root


def test_default_floor_and_explicit_legacy_baseline(tmp_path: Path) -> None:
    root = _package(tmp_path, "healthy.py", "sqlite.py")
    evidence = _coverage(
        {
            str(root / "healthy.py"): 89.5,
            str(root / "sqlite.py"): 59.0,
        }
    )

    measured = validate_package_files(
        evidence,
        root,
        baselines={"sqlite.py": 59.0},
    )

    assert measured == {"healthy.py": 89.5, "sqlite.py": 59.0}
    assert DEFAULT_THRESHOLD == 80.0


def test_new_or_existing_file_below_default_floor_fails(tmp_path: Path) -> None:
    root = _package(tmp_path, "new_adapter.py")
    with pytest.raises(ValueError, match=r"new_adapter\.py: 79\.99% < required 80\.00%"):
        validate_package_files(_coverage({str(root / "new_adapter.py"): 79.99}), root)


def test_legacy_baseline_is_a_non_regression_ratchet(tmp_path: Path) -> None:
    root = _package(tmp_path, "sqlite.py")
    with pytest.raises(ValueError, match=r"sqlite\.py: 58\.99% < required 59\.00%"):
        validate_package_files(
            _coverage({str(root / "sqlite.py"): 58.99}),
            root,
            baselines={"sqlite.py": 59.0},
        )


def test_missing_measurement_and_stale_baseline_fail_closed(tmp_path: Path) -> None:
    root = _package(tmp_path, "measured.py", "missing.py")
    with pytest.raises(ValueError, match="missing.py: missing coverage evidence"):
        validate_package_files(_coverage({str(root / "measured.py"): 100.0}), root)

    with pytest.raises(ValueError, match="baselines reference missing files"):
        validate_package_files(
            _coverage(
                {
                    str(root / "measured.py"): 100.0,
                    str(root / "missing.py"): 100.0,
                }
            ),
            root,
            baselines={"deleted.py": 50.0},
        )


def test_invalid_thresholds_percentages_and_shapes_fail_closed(tmp_path: Path) -> None:
    root = _package(tmp_path, "module.py")
    evidence = _coverage({str(root / "module.py"): 100.0})

    for threshold in (-0.1, 100.1):
        with pytest.raises(ValueError, match="threshold must be between 0 and 100"):
            validate_package_files(evidence, root, threshold=threshold)

    with pytest.raises(ValueError, match="baseline .* between 0 and 100"):
        validate_package_files(evidence, root, baselines={"module.py": -1.0})
    with pytest.raises(ValueError, match="cannot exceed default threshold"):
        validate_package_files(evidence, root, baselines={"module.py": 81.0})

    malformed = {"files": {str(root / "module.py"): {"summary": {"percent_covered": True}}}}
    with pytest.raises(TypeError, match="must be numeric"):
        validate_package_files(malformed, root)


def test_load_coverage_requires_files_object(tmp_path: Path) -> None:
    valid = tmp_path / "valid.json"
    valid.write_text(json.dumps(_coverage({"python/studio_storage/module.py": 90.0})), encoding="utf-8")
    assert "files" in load_coverage(valid)

    for content in ("[]", '{"files": []}'):
        invalid = tmp_path / "invalid.json"
        invalid.write_text(content, encoding="utf-8")
        with pytest.raises(TypeError, match="coverage evidence"):
            load_coverage(invalid)
