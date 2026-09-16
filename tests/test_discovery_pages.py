import pytest
from studio_connectors import DiscoveryPage


def test_discovery_page_rejects_cursor_without_truncation() -> None:
    with pytest.raises(ValueError, match="non-truncated"):
        DiscoveryPage(("asset",), "cursor", False)
