from __future__ import annotations

import pytest
from studio_core import ReproducibleManifest


def _manifest() -> ReproducibleManifest:
    return ReproducibleManifest(
        source_revision="git:abc123",
        environment="dev",
        runtime_profile="local",
        dependency_locks=(("python", "sha256:deps"),),
        plugin_lock="sha256:plugins",
        configuration=(("log_level", "INFO"),),
        execution_profile="local-process",
    )


def test_reproducible_manifest_round_trips_and_has_stable_identity() -> None:
    first = _manifest()
    second = ReproducibleManifest.from_json(first.to_json())
    assert second == first
    assert second.identity == first.identity


def test_reproducible_manifest_rejects_secrets_and_unknown_keys() -> None:
    with pytest.raises(ValueError, match="secret-like"):
        ReproducibleManifest(
            source_revision="git:abc123",
            environment="dev",
            runtime_profile="local",
            dependency_locks=(),
            plugin_lock="sha256:plugins",
            configuration=(("api_token", "do-not-store"),),
            execution_profile="local-process",
        )
    data = _manifest().to_data()
    data["unknown"] = "reject"
    with pytest.raises(ValueError, match="keys mismatch"):
        ReproducibleManifest.from_data(data)


def test_reproducible_manifest_requires_canonical_lock_order() -> None:
    with pytest.raises(ValueError, match="sorted"):
        ReproducibleManifest(
            source_revision="git:abc123",
            environment="dev",
            runtime_profile="local",
            dependency_locks=(("z", "1"), ("a", "2")),
            plugin_lock="sha256:plugins",
            configuration=(),
            execution_profile="local-process",
        )
