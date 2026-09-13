"""Provider-neutral executable connector registry."""

from __future__ import annotations

from collections.abc import Iterable

from .contracts import Connector


class ConnectorRegistry:
    """Resolve executable connectors by stable connector_id without fallback guessing."""

    def __init__(self, connectors: Iterable[Connector] = ()) -> None:
        by_id: dict[str, Connector] = {}
        for connector in connectors:
            connector_id = connector.descriptor.connector_id
            if connector_id in by_id:
                raise ValueError(f"duplicate executable connector id: {connector_id}")
            by_id[connector_id] = connector
        self._by_id = by_id

    def get(self, connector_id: str) -> Connector | None:
        return self._by_id.get(connector_id)

    def require(self, connector_id: str) -> Connector:
        connector = self.get(connector_id)
        if connector is None:
            raise KeyError(f"no executable connector registered: {connector_id}")
        return connector

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_id))


__all__ = ("ConnectorRegistry",)
