from __future__ import annotations

import pytest
from studio_connectors import ConnectorCapabilityRecord, ConnectorRegistry
from studio_core import ConnectorCapabilities, ConnectorDescriptor


class _Connector:
    def __init__(self, connector_id: str, capabilities: ConnectorCapabilities) -> None:
        self.descriptor = ConnectorDescriptor(connector_id, 1, capabilities)


def test_capability_registry_returns_deterministic_normalized_records() -> None:
    registry = ConnectorRegistry(
        (
            _Connector("z-source", ConnectorCapabilities(read=True, schema=True)),
            _Connector(
                "a-source",
                ConnectorCapabilities(
                    read=True,
                    incremental=True,
                    watermark_types=("timestamp",),
                    auth_modes=("secret-ref",),
                    max_batch_size=100,
                ),
            ),
        )
    )
    records = registry.capability_records()
    assert all(isinstance(record, ConnectorCapabilityRecord) for record in records)
    assert [record.connector_id for record in records] == ["a-source", "z-source"]
    assert records[0].capabilities.watermark_types == ("timestamp",)
    assert records[0].capabilities.max_batch_size == 100


def test_capabilities_validate_incremental_and_bounds() -> None:
    with pytest.raises(ValueError, match="requires read"):
        ConnectorCapabilities(incremental=True)
    with pytest.raises(ValueError, match="positive"):
        ConnectorCapabilities(read=True, max_page_size=0)
    with pytest.raises(ValueError, match="unique"):
        ConnectorCapabilities(read=True, auth_modes=("secret-ref", "secret-ref"))


def test_capability_payload_is_deterministic_and_json_ready() -> None:
    registry = ConnectorRegistry(
        [
            _Connector("z", ConnectorCapabilities(read=True, auth_modes=("secret-ref",))),
            _Connector("a", ConnectorCapabilities(discover=True, lineage=True)),
        ]
    )
    payload = registry.capability_payload()
    assert payload["count"] == 2
    assert [item["connector_id"] for item in payload["items"]] == ["a", "z"]
    assert payload["items"][1]["capabilities"]["auth_modes"] == ["secret-ref"]
