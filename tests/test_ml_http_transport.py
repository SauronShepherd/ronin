import pytest

from studio_ml.remote import urllib_json_transport


def test_http_transport_rejects_unsafe_base_urls() -> None:
    with pytest.raises(ValueError, match="http or https"):
        urllib_json_transport("file:///tmp/provider")
