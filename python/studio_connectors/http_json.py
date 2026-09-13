"""Bounded HTTP JSON connector with deployment-local secret resolution."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote, urlsplit

from studio_core import (
    AssetHandle,
    ConnectionDefinition,
    ConnectorCapabilities,
    ConnectorDescriptor,
    DiscoveredAsset,
    FieldSchema,
    SourceCheckpoint,
)
from studio_storage.secrets import SecretResolver

from .contracts import ConnectorReadResult


class HttpConnectorDependencyError(RuntimeError):
    """Raised when the optional HTTP client dependency is unavailable."""


def _httpx() -> Any:
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise HttpConnectorDependencyError(
            "HTTP connector support requires the optional Ronin data-plane dependencies"
        ) from exc
    return httpx


def _options(connection: ConnectionDefinition) -> dict[str, str]:
    return dict(connection.options)


def _secret_refs(connection: ConnectionDefinition) -> dict[str, object]:
    return dict(connection.secret_refs)


def _type_name(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return type(value).__name__


def _infer_fields(rows: tuple[dict[str, object], ...]) -> tuple[FieldSchema, ...]:
    if not rows:
        return ()
    names = tuple(sorted(rows[0]))
    expected = set(names)
    for row in rows:
        if set(row) != expected:
            raise ValueError("HTTP JSON records must have a consistent object shape")
    fields: list[FieldSchema] = []
    for name in names:
        values = [row[name] for row in rows]
        non_null = [value for value in values if value is not None]
        types = sorted({_type_name(value) for value in non_null})
        type_name = types[0] if len(types) == 1 else "json"
        fields.append(FieldSchema(name, type_name, any(value is None for value in values)))
    return tuple(fields)


class HttpJsonConnector:
    """Read bounded JSON records from one base URL without implicit redirect trust."""

    descriptor = ConnectorDescriptor(
        "http.json",
        1,
        ConnectorCapabilities(read=True),
    )

    def _validate(self, connection: ConnectionDefinition) -> tuple[str, dict[str, str]]:
        if connection.connector_id != self.descriptor.connector_id:
            raise ValueError("connection does not target the HTTP JSON connector")
        options = _options(connection)
        base_url = options.get("base_url")
        if base_url is None:
            raise ValueError("HTTP connection requires base_url")
        parsed = urlsplit(base_url)
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("HTTP base_url must not embed credentials")
        allow_http = options.get("allow_http", "false").casefold() == "true"
        if parsed.scheme not in ({"https", "http"} if allow_http else {"https"}):
            raise ValueError("HTTP base_url must use HTTPS unless allow_http=true")
        if not parsed.hostname:
            raise ValueError("HTTP base_url requires a hostname")
        if parsed.query or parsed.fragment:
            raise ValueError("HTTP base_url must not contain query or fragment components")
        return base_url.rstrip("/"), options

    def discover(
        self,
        connection: ConnectionDefinition,
        secrets: SecretResolver,
    ) -> tuple[DiscoveredAsset, ...]:
        del secrets
        self._validate(connection)
        return ()

    def read(
        self,
        connection: ConnectionDefinition,
        asset: AssetHandle,
        secrets: SecretResolver,
        *,
        limit: int = 10_000,
        checkpoint: SourceCheckpoint | None = None,
    ) -> ConnectorReadResult:
        if checkpoint is not None:
            raise ValueError("HTTP JSON connector does not yet support incremental checkpoints")
        if limit < 1 or limit > 100_000:
            raise ValueError("HTTP read limit must be between 1 and 100000")
        if asset.connection_id != connection.id:
            raise ValueError("HTTP asset handle belongs to a different connection")
        base_url, options = self._validate(connection)
        components = (*asset.namespace, asset.name)
        if any(not part or part in {".", ".."} or "://" in part for part in components):
            raise ValueError("HTTP asset path contains an unsafe component")
        path = "/".join(quote(part, safe="-._~") for part in components)
        url = f"{base_url}/{path}"

        headers = {"Accept": "application/json"}
        refs = _secret_refs(connection)
        bearer = refs.get("bearer_token")
        if bearer is not None:
            material = secrets.resolve(bearer)  # type: ignore[arg-type]
            headers["Authorization"] = f"Bearer {material.reveal_text()}"

        httpx = _httpx()
        timeout_seconds = float(options.get("timeout_seconds", "30"))
        if timeout_seconds <= 0 or timeout_seconds > 300:
            raise ValueError("HTTP timeout_seconds must be in (0, 300]")
        with httpx.Client(follow_redirects=False, timeout=timeout_seconds) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            body = response.content
            payload = response.json()

        records_key = options.get("records_key")
        if records_key is not None:
            if not isinstance(payload, Mapping):
                raise ValueError("HTTP records_key requires a JSON object response")
            payload = payload.get(records_key)
        if not isinstance(payload, list):
            raise ValueError("HTTP JSON response must resolve to an array of records")
        if len(payload) > limit:
            raise ValueError("HTTP JSON response exceeds requested row limit")
        if not all(isinstance(item, Mapping) for item in payload):
            raise ValueError("HTTP JSON records must be objects")
        rows = tuple(dict(item) for item in payload)
        fields = _infer_fields(rows)
        checkpoint_value = hashlib.sha256(body).hexdigest()
        return ConnectorReadResult(
            fields,
            rows,
            SourceCheckpoint("snapshot", checkpoint_value),
        )


__all__ = ("HttpConnectorDependencyError", "HttpJsonConnector")
