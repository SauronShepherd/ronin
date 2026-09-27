import pytest

from studio_data_engineering import RuntimeHandshake, negotiate_runtime


def test_registered_runtime_handshake_exposes_capabilities() -> None:
    handshake = negotiate_runtime("spark-connect", required_capabilities=("logical-plan",))
    assert handshake.provider == "spark-connect"
    assert handshake.supports(("batch", "dataframe"))


def test_runtime_negotiation_fails_closed_for_missing_capability() -> None:
    with pytest.raises(ValueError, match="lacks required capabilities"):
        negotiate_runtime("local-preview", required_capabilities=("stream",))


def test_configured_provider_overrides_local_contract() -> None:
    class Provider:
        def handshake(self):
            return RuntimeHandshake("spark-connect", "test-provider", "1", frozenset({"batch"}))

    with pytest.raises(ValueError, match="lacks required capabilities"):
        negotiate_runtime(
            "spark-connect",
            required_capabilities=("logical-plan",),
            providers={"spark-connect": Provider()},
        )
