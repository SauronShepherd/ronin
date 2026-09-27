import pytest

from studio_connectors import (
    AzureBlobJsonConnector,
    DiscoveryPage,
    JdbcConnector,
    OzoneJsonConnector,
    PagedConnector,
    S3JsonConnector,
)


def test_discovery_page_rejects_cursor_without_truncation() -> None:
    with pytest.raises(ValueError, match="non-truncated"):
        DiscoveryPage(("asset",), "cursor", False)


def test_paged_connector_capability_is_explicit() -> None:
    assert isinstance(S3JsonConnector(client=object()), PagedConnector)
    assert isinstance(OzoneJsonConnector(client=object()), PagedConnector)
    assert isinstance(AzureBlobJsonConnector(container_client=object()), PagedConnector)
    assert isinstance(JdbcConnector(connect=lambda *_args: object()), PagedConnector)
