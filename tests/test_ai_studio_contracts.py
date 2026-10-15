import pytest
from studio_ai_studio.contracts import (
    AdapterKind,
    Capability,
    EndpointConfig,
    EndpointId,
    ModelSnapshot,
    PublicModelName,
    RequestLimits,
)
from studio_ai_studio.errors import EndpointSaturated, ModelNotFound


def test_endpoint_and_model_contracts_are_deterministic():
    endpoint = EndpointConfig(
        EndpointId("ollama"),
        AdapterKind.OLLAMA,
        "http://127.0.0.1:11434",
        (PublicModelName("qwen"),),
    )
    snapshot = ModelSnapshot(
        endpoint.id, "qwen2.5", PublicModelName("qwen"), frozenset({Capability.CHAT})
    )
    assert endpoint.models == (PublicModelName("qwen"),)
    assert snapshot.endpoint_id == endpoint.id


@pytest.mark.parametrize("value", ["", " Ollama", "OLLAMA", "../x", "a/b"])
def test_endpoint_id_is_path_safe(value):
    with pytest.raises(ValueError, match="endpoint id"):
        EndpointId(value)


def test_limits_and_endpoint_reject_unsafe_values():
    with pytest.raises(ValueError, match="limits"):
        RequestLimits(max_body_bytes=10)
    with pytest.raises(ValueError, match="credentials"):
        EndpointConfig(
            EndpointId("x"),
            AdapterKind.OLLAMA,
            "https://u:p@example.com",
            (PublicModelName("m"),),
        )


def test_errors_have_stable_wire_properties():
    assert ModelNotFound("qwen").status == 404
    assert EndpointSaturated("ollama").retryable is True
