import json
from pathlib import Path

import pytest

from tools.mutation_gate import MUTATION_THRESHOLD, load_stats, mutation_score, validate_stats


def _stats(**overrides: object) -> dict[str, object]:
    stats: dict[str, object] = {
        "killed": 90,
        "survived": 10,
        "total": 100,
        "no_tests": 0,
        "skipped": 0,
        "suspicious": 0,
        "timeout": 0,
        "check_was_interrupted_by_user": 0,
        "segfault": 0,
    }
    stats.update(overrides)
    return stats


def test_mutation_score_and_threshold_boundary() -> None:
    stats = _stats()
    assert mutation_score(stats) == MUTATION_THRESHOLD  # type: ignore[arg-type]
    validate_stats(stats)

    skipped = _stats(killed=9, survived=1, total=20, skipped=10)
    assert mutation_score(skipped) == 90.0  # type: ignore[arg-type]
    validate_stats(skipped)

    empty = _stats(killed=0, survived=0, total=5, skipped=5)
    assert mutation_score(empty) == 0.0  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="below threshold"):
        validate_stats(empty)


def test_gate_rejects_low_score_and_invalid_evidence() -> None:
    with pytest.raises(ValueError, match="below threshold"):
        validate_stats(_stats(killed=89, survived=11))

    for key in ("no_tests", "suspicious", "timeout", "check_was_interrupted_by_user", "segfault"):
        stats = _stats(killed=99, survived=0, **{key: 1})
        with pytest.raises(ValueError, match="invalid evidence"):
            validate_stats(stats)


def test_gate_rejects_malformed_stats_and_thresholds() -> None:
    stats = _stats()
    del stats["killed"]
    with pytest.raises(ValueError, match="missing keys"):
        validate_stats(stats)

    with pytest.raises(TypeError, match="integers"):
        validate_stats(_stats(killed=True))
    with pytest.raises(ValueError, match="non-negative"):
        validate_stats(_stats(killed=-1, survived=101))
    with pytest.raises(ValueError, match="inconsistent"):
        validate_stats(_stats(total=101))
    for threshold in (-0.1, 100.1):
        with pytest.raises(ValueError, match="between 0 and 100"):
            validate_stats(_stats(), threshold)


def test_load_stats_requires_json_object_with_string_keys(tmp_path: Path) -> None:
    valid = tmp_path / "valid.json"
    valid.write_text(json.dumps(_stats()), encoding="utf-8")
    assert load_stats(valid) == _stats()

    array = tmp_path / "array.json"
    array.write_text("[]", encoding="utf-8")
    with pytest.raises(TypeError, match="JSON object"):
        load_stats(array)
