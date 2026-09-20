import pytest
from studio_ai_studio.security import NetworkPolicy, NetworkPolicyError, validate_endpoint_url


def test_loopback_http_requires_explicit_local_policy():
    with pytest.raises(NetworkPolicyError, match="scheme"):
        validate_endpoint_url("http://127.0.0.1:11434")
    assert validate_endpoint_url(
        "http://127.0.0.1:11434", policy=NetworkPolicy(allow_http=True)
    ) == "127.0.0.1"


def test_credentials_query_and_unresolved_host_are_rejected():
    for url in (
        "https://user:pass@example.com",
        "https://example.com/?token=x",
        "https://does-not-exist.invalid",
    ):
        with pytest.raises(NetworkPolicyError):
            validate_endpoint_url(url)


def test_private_address_needs_explicit_policy():
    with pytest.raises(NetworkPolicyError, match="loopback"):
        validate_endpoint_url("https://127.0.0.1", policy=NetworkPolicy(allow_loopback=False))
