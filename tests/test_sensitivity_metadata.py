import pytest

from studio_core import SensitivityMetadata


def test_sensitivity_metadata_resolves_and_round_trips_canonically() -> None:
    metadata = SensitivityMetadata(
        2,
        explicit=("pii", "confidential"),
        inherited=("internal", "retention-7y"),
        inherited_from=("workspace/root",),
    )
    assert metadata.effective == ("confidential", "internal", "pii", "retention-7y")
    assert metadata.effective_level == "confidential"
    assert SensitivityMetadata.from_json(metadata.to_json()) == metadata
    assert metadata.to_payload()["effective"] == list(metadata.effective)


def test_sensitivity_metadata_rejects_noncanonical_or_unsafe_state() -> None:
    with pytest.raises(ValueError, match="positive"):
        SensitivityMetadata(0)
    with pytest.raises(ValueError, match="non-empty"):
        SensitivityMetadata(1, explicit=(" ",))
    metadata = SensitivityMetadata(1, explicit=("public",))
    payload = metadata.to_payload()
    payload["effective"] = ["restricted"]
    with pytest.raises(ValueError, match="not canonical"):
        SensitivityMetadata.from_payload(payload)
