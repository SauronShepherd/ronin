import pytest
from studio_kernel import (
    EffectiveRuntimeSetting,
    ExecutionAttemptId,
    ExecutionEventId,
    ExecutionReproducibilitySnapshot,
    ReproducibilityDigest,
)


def test_attempt_and_event_identity_are_explicit_and_deterministic() -> None:
    attempt = ExecutionAttemptId("run-42/attempt-2")
    first = ExecutionEventId(attempt, 0)
    second = ExecutionEventId(attempt, 1)

    assert str(attempt) == "run-42/attempt-2"
    assert first < second

    for value in ("", " padded ", "bad\nvalue"):
        with pytest.raises(ValueError, match="execution attempt id"):
            ExecutionAttemptId(value)
    with pytest.raises(ValueError, match="non-negative"):
        ExecutionEventId(attempt, -1)


def test_effective_settings_are_canonical_and_reject_secret_bearing_names() -> None:
    alpha = EffectiveRuntimeSetting("engine.mode", "batch")
    zeta = EffectiveRuntimeSetting("spark.version", "4.0.1")
    snapshot = ExecutionReproducibilitySnapshot(settings=(zeta, alpha))

    assert snapshot.settings == (alpha, zeta)

    for name in (
        "db.password",
        "access-token",
        "client_secret",
        "service.credentials",
        "authorization",
        "api.key",
        "private-key",
    ):
        with pytest.raises(ValueError, match="secret material"):
            EffectiveRuntimeSetting(name, "do-not-persist")

    for invalid in ("", " padded ", "bad\nvalue"):
        with pytest.raises(ValueError, match="runtime setting name"):
            EffectiveRuntimeSetting(invalid, "value")
        with pytest.raises(ValueError, match="runtime setting value"):
            EffectiveRuntimeSetting("engine.mode", invalid)

    with pytest.raises(ValueError, match="setting names must be unique"):
        ExecutionReproducibilitySnapshot(
            settings=(
                EffectiveRuntimeSetting("engine.mode", "batch"),
                EffectiveRuntimeSetting("engine.mode", "streaming"),
            )
        )


def test_reproducibility_digests_are_typed_canonical_and_unique() -> None:
    image = ReproducibilityDigest("runtime_image", "python:3.12-slim", "a" * 64)
    lock = ReproducibilityDigest("package_lock", "uv.lock", "b" * 64)
    environment = ReproducibilityDigest("environment", "python-env", "c" * 64)
    artifact = ReproducibilityDigest("runtime_artifact", "kernel.tar.zst", "d" * 64)
    snapshot = ExecutionReproducibilitySnapshot(digests=(image, lock, environment, artifact))

    assert snapshot.digests == tuple(sorted((image, lock, environment, artifact)))

    with pytest.raises(ValueError, match="unsupported reproducibility digest kind"):
        ReproducibilityDigest("unknown", "ref", "a" * 64)  # type: ignore[arg-type]
    for reference in ("", " padded ", "bad\nref"):
        with pytest.raises(ValueError, match="digest reference"):
            ReproducibilityDigest("environment", reference, "a" * 64)
    for digest in ("a" * 63, "A" * 64, "z" * 64):
        with pytest.raises(ValueError, match="lowercase SHA-256"):
            ReproducibilityDigest("environment", "python-env", digest)

    with pytest.raises(ValueError, match="kind/reference pairs must be unique"):
        ExecutionReproducibilitySnapshot(
            digests=(
                ReproducibilityDigest("package_lock", "uv.lock", "a" * 64),
                ReproducibilityDigest("package_lock", "uv.lock", "b" * 64),
            )
        )
